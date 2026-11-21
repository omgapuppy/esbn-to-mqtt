from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from esbn_to_mqtt import statistics
from esbn_to_mqtt.models import MeterReading
from esbn_to_mqtt.statistics import (
    StatisticsError,
    hourly_import,
    plan_updates,
    statistic_id,
    sync_hourly_import,
)
from websockets.sync.server import ServerConnection, serve

START = datetime(2026, 10, 25, tzinfo=UTC)
MPRN = "10000000000"


def hour(offset: int) -> datetime:
    return START + timedelta(hours=offset)


def readings(first: int, *amounts: float) -> list[MeterReading]:
    return [
        MeterReading(hour(offset) + timedelta(minutes=minute), import_kwh=amount / 2)
        for offset, amount in enumerate(amounts, first)
        for minute in (0, 30)
    ]


def test_hourly_import_keeps_both_autumn_folds_and_skips_partial_hours() -> None:
    dublin = ZoneInfo("Europe/Dublin")
    source = [
        MeterReading(r.timestamp.astimezone(dublin), import_kwh=r.import_kwh)
        for r in readings(0, 1.0, 2.0, 3.0)[:-1]
    ]
    source.append(MeterReading(hour(2) + timedelta(minutes=30), export_kwh=3.0))
    assert hourly_import(source) == {hour(0): 1.0, hour(1): 2.0}


def test_statistic_is_stable_and_unique_per_meter() -> None:
    identifier = statistic_id(MPRN)
    assert identifier.startswith("esbn:grid_import_")
    assert MPRN not in identifier
    assert identifier == statistic_id(MPRN)
    assert identifier != statistic_id("10000000001")


def test_rolling_window_and_state_loss_keep_the_recorder_baseline() -> None:
    recorded = {hour(0): 99, hour(1): 100, hour(2): 101}
    available = hourly_import(readings(2, 1.0, 1.0))
    assert plan_updates(available, recorded) == [(hour(3), 102.0)]


def test_revision_updates_the_dependent_suffix_and_is_idempotent() -> None:
    recorded = {hour(0): 100, hour(1): 101, hour(2): 102, hour(3): 103}
    available = hourly_import(readings(1, 1.0, 3.0, 1.0, 1.0))
    expected = [(hour(2), 104.0), (hour(3), 105.0), (hour(4), 106.0)]
    assert plan_updates(available, recorded) == expected
    recorded.update(expected[:1])
    assert plan_updates(available, recorded) == expected[1:]
    recorded.update(expected[1:])
    assert plan_updates(available, recorded) == []


def test_older_backfill_preserves_recorded_totals_and_changes_the_suffix() -> None:
    recorded = {hour(0): 100, hour(2): 102, hour(3): 103}
    available = hourly_import(readings(1, 1.0, 2.0, 1.0))
    assert plan_updates(available, recorded) == [
        (hour(1), 101.0),
        (hour(2), 103.0),
        (hour(3), 104.0),
    ]


def test_revision_with_missing_recorded_hour_refuses_all_updates() -> None:
    recorded = {hour(0): 100, hour(1): 101, hour(2): 102}
    available = hourly_import(readings(1, 2.0))
    with pytest.raises(StatisticsError, match="missing a previously imported hour"):
        plan_updates(available, recorded)


@pytest.fixture
def recorder() -> Iterator[tuple[str, dict[datetime, float], list[dict[str, object]]]]:
    totals: dict[datetime, float] = {hour(0): 100.0}
    commands: list[dict[str, object]] = []

    def handle(socket: ServerConnection) -> None:
        socket.send(json.dumps({"type": "auth_required"}))
        auth = json.loads(socket.recv())
        if auth != {"type": "auth", "access_token": "test-token"}:
            socket.send(json.dumps({"type": "auth_invalid"}))
            return
        socket.send(json.dumps({"type": "auth_ok"}))
        for raw in socket:
            request = json.loads(raw)
            commands.append(request)
            payload = {"type": "result", "id": request["id"], "success": True}
            if request["type"] == "recorder/statistics_during_period":
                payload["result"] = {
                    statistic_id(MPRN): [
                        {"start": int(start.timestamp() * 1000), "sum": total}
                        for start, total in totals.items()
                    ],
                }
            elif request["type"] == "recorder/import_statistics":
                for row in request["stats"]:
                    totals[datetime.fromisoformat(row["start"])] = row["sum"]
            else:
                raise AssertionError(request)
            socket.send(json.dumps(payload))

    with serve(handle, "127.0.0.1", 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield f"ws://127.0.0.1:{server.socket.getsockname()[1]}", totals, commands
        server.shutdown()
        thread.join()


def test_websocket_reads_before_writing_and_only_sends_changed_rows(
    recorder: tuple[str, dict[datetime, float], list[dict[str, object]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url, totals, commands = recorder
    monkeypatch.setattr(statistics, "IMPORT_BATCH_SIZE", 1)
    source = readings(1, 1.0, 2.0)

    assert sync_hourly_import(source, MPRN, url=url, token="test-token") == 2
    assert totals == {hour(0): 100.0, hour(1): 101.0, hour(2): 103.0}
    assert [command["type"] for command in commands] == [
        "recorder/statistics_during_period",
        "recorder/import_statistics",
        "recorder/import_statistics",
    ]
    assert commands[0]["statistic_ids"] == [statistic_id(MPRN)]
    assert commands[0]["types"] == ["sum"]
    assert commands[1]["metadata"] == {
        "has_sum": True,
        "mean_type": 0,
        "name": f"ESBN Hourly Grid Import ({statistic_id(MPRN)[-6:]})",
        "source": "esbn",
        "statistic_id": statistic_id(MPRN),
        "unit_class": "energy",
        "unit_of_measurement": "kWh",
    }
    assert sync_hourly_import(source, MPRN, url=url, token="test-token") == 0
    assert len(commands) == 4


def test_websocket_does_not_write_on_auth_failure(
    recorder: tuple[str, dict[datetime, float], list[dict[str, object]]],
) -> None:
    url, _, commands = recorder
    with pytest.raises(StatisticsError, match="rejected the app token"):
        sync_hourly_import(readings(0, 1.0), MPRN, url=url, token="bad")
    assert commands == []


def test_no_complete_hour_skips_websocket() -> None:
    assert sync_hourly_import(readings(0, 1.0)[:1], MPRN, url="ws://127.0.0.1:1") == 0
