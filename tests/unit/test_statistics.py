# tests/unit/test_statistics.py
from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from esbn_to_mqtt import main, statistics
from esbn_to_mqtt.config import ConfigError, load_config_dict
from esbn_to_mqtt.models import StatisticsConfig
from esbn_to_mqtt.state import AccumulatorState
from esbn_to_mqtt.statistics import (
    HourlyStatistic,
    StatisticsError,
    build_hourly_import_statistics,
    import_hourly_statistics,
)
from websockets.sync.server import ServerConnection, serve


def _half_hours(start: str, values: list[float], channel: str = "import") -> dict[str, float]:
    # Consecutive 30-minute interval keys starting at `start` (UTC ISO timestamp).
    first = datetime.fromisoformat(start)
    return {
        f"{datetime.fromtimestamp(first.timestamp() + 1800 * i, UTC).isoformat()}:{channel}": v
        for i, v in enumerate(values)
    }


# ---------- hourly aggregation ----------


def test_pairs_half_hours_into_hours_with_running_total() -> None:
    values = _half_hours("2026-11-01T10:00:00+00:00", [0.1, 0.2, 0.3, 0.4])

    result = build_hourly_import_statistics(values)

    assert [s.start for s in result] == [
        datetime(2026, 11, 1, 10, tzinfo=UTC),
        datetime(2026, 11, 1, 11, tzinfo=UTC),
    ]
    assert [s.kwh for s in result] == [0.3, 0.7]
    assert [s.cumulative_kwh for s in result] == [0.3, 1.0]


def test_skips_incomplete_hours() -> None:
    # 10:00 complete, 11:00 has only its first half-hour, 12:30 has only its second.
    values = _half_hours("2026-11-01T10:00:00+00:00", [0.1, 0.2, 0.3])
    values.update(_half_hours("2026-11-01T12:30:00+00:00", [0.5]))

    result = build_hourly_import_statistics(values)

    assert [s.start.hour for s in result] == [10]
    assert result[0].cumulative_kwh == 0.3


def test_ignores_export_values_and_empty_input() -> None:
    export_only = _half_hours("2026-11-01T10:00:00+00:00", [1.0, 1.0], channel="export")

    assert build_hourly_import_statistics(export_only) == []
    assert build_hourly_import_statistics({}) == []


def test_orders_hours_regardless_of_input_order() -> None:
    values = _half_hours("2026-11-01T10:00:00+00:00", [0.1, 0.1, 0.2, 0.2])
    shuffled = dict(reversed(list(values.items())))

    assert build_hourly_import_statistics(shuffled) == build_hourly_import_statistics(values)


def test_converts_local_offsets_to_utc_hours() -> None:
    # 01:00 and 01:30 in IST (+01:00) is the 00:00 UTC hour.
    values = {
        "2026-10-24T01:00:00+01:00:import": 0.25,
        "2026-10-24T01:30:00+01:00:import": 0.25,
    }

    result = build_hourly_import_statistics(values)

    assert [s.start for s in result] == [datetime(2026, 10, 24, 0, tzinfo=UTC)]


def test_autumn_repeated_local_hour_stays_two_separate_hours() -> None:
    # 25 Oct 2026: local 01:00-02:00 happens twice, once in IST (UTC 00:00) and once in GMT
    # (UTC 01:00). They must remain two hours, never merged into one.
    values = _half_hours("2026-10-25T00:00:00+00:00", [0.1, 0.1, 0.2, 0.2])

    result = build_hourly_import_statistics(values)

    assert [s.start.hour for s in result] == [0, 1]
    assert [s.kwh for s in result] == [0.2, 0.4]


def test_totals_ignore_how_much_history_the_download_window_holds() -> None:
    # A rolling ESBN window only matters if totals were built from the window. They come
    # from the stored intervals, so the same stored data always gives the same series.
    stored = _half_hours("2026-11-01T00:00:00+00:00", [0.1] * 48)
    state = AccumulatorState(
        import_total_kwh=4.8,
        export_total_kwh=None,
        last_interval_start=None,
        processed_intervals=frozenset(stored),
        processed_interval_values=stored,
    )

    result = build_hourly_import_statistics(state.processed_interval_values)

    assert len(result) == 24
    assert result[-1].cumulative_kwh == pytest.approx(4.8)


# ---------- websocket import ----------


class FakeHomeAssistant:
    """A minimal Home Assistant websocket: auth handshake, then recorder/import_statistics."""

    def __init__(
        self,
        *,
        auth_ok: bool = True,
        import_success: bool = True,
        noise_before_result: bool = False,
    ) -> None:
        self.auth_ok = auth_ok
        self.import_success = import_success
        self.noise_before_result = noise_before_result
        self.auth: dict[str, Any] | None = None
        self.imports: list[dict[str, Any]] = []

    def handle(self, ws: ServerConnection) -> None:
        ws.send(json.dumps({"type": "auth_required"}))
        self.auth = json.loads(ws.recv())
        if not self.auth_ok:
            ws.send(json.dumps({"type": "auth_invalid"}))
            return
        ws.send(json.dumps({"type": "auth_ok"}))
        for raw in ws:
            message = json.loads(raw)
            self.imports.append(message)
            if self.noise_before_result:
                ws.send(json.dumps({"id": 999, "type": "event"}))
            reply: dict[str, Any] = {
                "id": message["id"],
                "type": "result",
                "success": self.import_success,
            }
            if not self.import_success:
                reply["error"] = {"code": "invalid_format", "message": "bad metadata"}
            ws.send(json.dumps(reply))


@pytest.fixture
def run_server() -> Iterator[Any]:
    servers: list[Any] = []

    def start(fake: FakeHomeAssistant) -> str:
        server = serve(fake.handle, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        port = server.socket.getsockname()[1]
        return f"ws://127.0.0.1:{port}"

    yield start
    for server in servers:
        server.shutdown()


def _hours(count: int) -> list[HourlyStatistic]:
    midnight = datetime(2026, 11, 1, tzinfo=UTC)
    return [
        HourlyStatistic(
            start=datetime.fromtimestamp(midnight.timestamp() + 3600 * i, UTC),
            kwh=0.5,
            cumulative_kwh=0.5 * (i + 1),
        )
        for i in range(count)
    ]


def test_import_authenticates_and_sends_expected_payload(run_server: Any) -> None:
    fake = FakeHomeAssistant()
    url = run_server(fake)

    sent = import_hourly_statistics(_hours(2), StatisticsConfig(), url=url, token="abc")

    assert sent == 2
    assert fake.auth == {"type": "auth", "access_token": "abc"}
    message = fake.imports[0]
    assert message["type"] == "recorder/import_statistics"
    assert message["metadata"] == {
        "has_sum": True,
        "mean_type": 0,
        "name": None,
        "source": "esbn",
        "statistic_id": "esbn:grid_import",
        "unit_class": "energy",
        "unit_of_measurement": "kWh",
    }
    assert message["stats"] == [
        {"start": "2026-11-01T00:00:00+00:00", "state": 0.5, "sum": 0.5},
        {"start": "2026-11-01T01:00:00+00:00", "state": 1.0, "sum": 1.0},
    ]


def test_import_splits_large_histories_into_chunks(
    run_server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(statistics, "CHUNK_SIZE", 2)
    fake = FakeHomeAssistant()
    url = run_server(fake)

    import_hourly_statistics(_hours(5), StatisticsConfig(), url=url, token="abc")

    assert [len(m["stats"]) for m in fake.imports] == [2, 2, 1]
    assert [m["id"] for m in fake.imports] == [1, 2, 3]
    # Every row carries an absolute running total, so chunk boundaries lose nothing.
    assert fake.imports[2]["stats"][0]["sum"] == 2.5


def test_import_uses_configured_statistic_id(run_server: Any) -> None:
    fake = FakeHomeAssistant()
    url = run_server(fake)
    config = StatisticsConfig(statistic_id="home:meter_import")

    import_hourly_statistics(_hours(1), config, url=url, token="abc")

    assert fake.imports[0]["metadata"]["source"] == "home"
    assert fake.imports[0]["metadata"]["statistic_id"] == "home:meter_import"


def test_import_ignores_unrelated_messages_while_waiting(run_server: Any) -> None:
    fake = FakeHomeAssistant(noise_before_result=True)
    url = run_server(fake)

    assert import_hourly_statistics(_hours(1), StatisticsConfig(), url=url, token="abc") == 1


def test_import_with_no_statistics_does_not_connect() -> None:
    assert import_hourly_statistics([], StatisticsConfig(), url="ws://127.0.0.1:1") == 0


def test_import_requires_a_token() -> None:
    with pytest.raises(StatisticsError, match="SUPERVISOR_TOKEN"):
        import_hourly_statistics(_hours(1), StatisticsConfig(), url="ws://127.0.0.1:1")


def test_import_reads_token_from_environment(
    run_server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUPERVISOR_TOKEN", "from-env")
    fake = FakeHomeAssistant()
    url = run_server(fake)

    import_hourly_statistics(_hours(1), StatisticsConfig(), url=url)

    assert fake.auth == {"type": "auth", "access_token": "from-env"}


def test_import_reports_rejected_token(run_server: Any) -> None:
    url = run_server(FakeHomeAssistant(auth_ok=False))

    with pytest.raises(StatisticsError, match="rejected"):
        import_hourly_statistics(_hours(1), StatisticsConfig(), url=url, token="bad")


def test_import_reports_refused_import(run_server: Any) -> None:
    url = run_server(FakeHomeAssistant(import_success=False))

    with pytest.raises(StatisticsError, match="bad metadata"):
        import_hourly_statistics(_hours(1), StatisticsConfig(), url=url, token="abc")


def test_import_reports_unreachable_home_assistant() -> None:
    with pytest.raises(StatisticsError, match="could not reach"):
        import_hourly_statistics(
            _hours(1), StatisticsConfig(), url="ws://127.0.0.1:1", token="abc"
        )


# ---------- config ----------


def _options() -> dict[str, object]:
    return {
        "esbn_username": "person@example.com",
        "esbn_password": "secret",
        "mprn": "10000000000",
        "mqtt_host": "core-mosquitto",
        "mqtt_port": 1883,
        "mqtt_username": "ha",
        "mqtt_password": "mqttpass",
        "poll_interval_hours": 24,
        "mqtt_discovery_prefix": "homeassistant",
        "mqtt_topic_prefix": "esbn_to_mqtt",
        "log_level": "info",
    }


def test_statistics_config_defaults_to_enabled_esbn_grid_import() -> None:
    config = load_config_dict(_options())

    assert config.statistics.enabled is True
    assert config.statistics.statistic_id == "esbn:grid_import"
    assert config.statistics.source == "esbn"


def test_statistics_config_accepts_overrides() -> None:
    options = _options() | {"statistics_enabled": False, "statistics_id": "home:meter_import"}

    config = load_config_dict(options)

    assert config.statistics.enabled is False
    assert config.statistics.statistic_id == "home:meter_import"


@pytest.mark.parametrize("bad_id", ["grid_import", "ESBN:grid", "esbn:grid import", "a:b:c"])
def test_statistics_config_rejects_invalid_ids(bad_id: str) -> None:
    with pytest.raises(ConfigError, match="statistics_id"):
        load_config_dict(_options() | {"statistics_id": bad_id})


# ---------- poll integration ----------


def _accumulator() -> AccumulatorState:
    stored = _half_hours("2026-11-01T10:00:00+00:00", [0.1, 0.2])
    return AccumulatorState(
        import_total_kwh=0.3,
        export_total_kwh=None,
        last_interval_start=None,
        processed_intervals=frozenset(stored),
        processed_interval_values=stored,
    )


def test_poll_publishes_hourly_statistics(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[Any] = []
    monkeypatch.setattr(
        main,
        "import_hourly_statistics",
        lambda stats, config: captured.append((stats, config)),
    )
    config = load_config_dict(_options())

    main._publish_hourly_statistics(config, _accumulator())

    stats, used_config = captured[0]
    assert [s.cumulative_kwh for s in stats] == [0.3]
    assert used_config.statistic_id == "esbn:grid_import"


def test_poll_skips_statistics_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    monkeypatch.setattr(main, "import_hourly_statistics", lambda *a, **k: called.append(True))
    config = load_config_dict(_options() | {"statistics_enabled": False})

    main._publish_hourly_statistics(config, _accumulator())

    assert called == []


def test_statistics_failure_is_logged_and_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise StatisticsError("could not reach Home Assistant: boom")

    monkeypatch.setattr(main, "import_hourly_statistics", fail)
    config = load_config_dict(_options())

    with caplog.at_level("ERROR"):
        main._publish_hourly_statistics(config, _accumulator())

    assert "hourly statistics import failed" in caplog.text
