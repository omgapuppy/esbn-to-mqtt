from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from esbn_to_mqtt import main
from esbn_to_mqtt.esbn import EsbnError
from esbn_to_mqtt.hdf import HdfParseError
from esbn_to_mqtt.models import AppConfig, EsbnCredentials, MqttConfig
from esbn_to_mqtt.mqtt import MqttMessage, MqttPublishError, build_availability_message
from esbn_to_mqtt.state import AccumulatorState


def app_config() -> AppConfig:
    return AppConfig(
        esbn=EsbnCredentials(
            username="esbn-user",
            password="esbn-pass",
            mprn="10000000000",
        ),
        mqtt=MqttConfig(
            host="core-mosquitto",
            port=1883,
            username="mqtt-user",
            password="mqtt-pass",
            discovery_prefix="homeassistant",
            topic_prefix="esbn_to_mqtt",
        ),
        poll_interval_hours=6,
        log_level="info",
    )


def test_main_once_swallows_mqtt_publish_error_and_redacts_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    config = app_config()
    published_messages: list[list[MqttMessage]] = []

    class FakePublisher:
        def __init__(self, mqtt_config: MqttConfig) -> None:
            self.mqtt_config = mqtt_config

        def publish_messages(self, messages: list[MqttMessage]) -> None:
            published_messages.append(messages)

    monkeypatch.setattr(sys, "argv", ["prog", "--once", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(main, "run_once", Mock(side_effect=MqttPublishError(
        "failed for mqtt-user mqtt-pass 10000000000"
    )))
    load_options_file = Mock(return_value=config)
    monkeypatch.setattr(main, "load_options_file", load_options_file)
    monkeypatch.setattr(main, "configure_logging", Mock())
    monkeypatch.setattr(main, "MqttPublisher", FakePublisher)
    monkeypatch.setattr(main.time, "sleep", Mock())

    with caplog.at_level("ERROR"):
        main.main()

    assert load_options_file.called
    assert published_messages == [
        [build_availability_message(config.mqtt, config.mprn, online=False)]
    ]
    assert "mqtt-user" not in caplog.text
    assert "mqtt-pass" not in caplog.text
    assert "10000000000" not in caplog.text
    assert "[REDACTED]" in caplog.text


@pytest.mark.parametrize("error", [EsbnError("boom"), MqttPublishError("boom")])
def test_main_publishes_offline_availability_after_runtime_error_without_cached_state(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    tmp_path: Path,
) -> None:
    config = app_config()
    published_messages: list[list[MqttMessage]] = []

    class FakePublisher:
        def __init__(self, mqtt_config: MqttConfig) -> None:
            self.mqtt_config = mqtt_config

        def publish_messages(self, messages: list[MqttMessage]) -> None:
            published_messages.append(messages)

    monkeypatch.setattr(sys, "argv", ["prog", "--once", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(main, "run_once", Mock(side_effect=error))
    monkeypatch.setattr(main, "load_options_file", Mock(return_value=config))
    monkeypatch.setattr(main, "configure_logging", Mock())
    monkeypatch.setattr(main, "MqttPublisher", FakePublisher)
    monkeypatch.setattr(main.time, "sleep", Mock())

    main.main()

    assert len(published_messages) == 1
    assert published_messages[0] == [
        build_availability_message(config.mqtt, config.mprn, online=False)
    ]


@pytest.mark.parametrize(
    "error",
    [
        EsbnError("boom"),
        HdfParseError("bad csv with esbn-user esbn-pass 10000000000"),
        MqttPublishError("boom"),
    ],
)
def test_main_keeps_cached_state_available_after_transient_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = app_config()
    AccumulatorState(
        import_total_kwh=1.23,
        export_total_kwh=None,
        last_interval_start=datetime(2026, 5, 13, 0, 0, tzinfo=UTC),
        processed_intervals=frozenset({"2026-05-13T00:00:00+00:00:import"}),
    ).save(tmp_path / "state.json")
    published_messages: list[list[MqttMessage]] = []

    class FakePublisher:
        def __init__(self, mqtt_config: MqttConfig) -> None:
            self.mqtt_config = mqtt_config

        def publish_messages(self, messages: list[MqttMessage]) -> None:
            published_messages.append(messages)

    monkeypatch.setattr(sys, "argv", ["prog", "--once", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(main, "run_once", Mock(side_effect=error))
    monkeypatch.setattr(main, "load_options_file", Mock(return_value=config))
    monkeypatch.setattr(main, "configure_logging", Mock())
    monkeypatch.setattr(main, "MqttPublisher", FakePublisher)
    monkeypatch.setattr(main.time, "sleep", Mock())

    with caplog.at_level("WARNING"):
        main.main()

    assert published_messages == []
    assert "keeping last known MQTT state available" in caplog.text
    assert "esbn-user" not in caplog.text
    assert "esbn-pass" not in caplog.text
    assert "10000000000" not in caplog.text


def test_main_uses_bounded_backoff_after_transient_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = app_config()
    sleep = Mock(side_effect=KeyboardInterrupt)

    monkeypatch.setattr(sys, "argv", ["prog"])
    monkeypatch.setattr(main, "run_once", Mock(side_effect=EsbnError("boom")))
    monkeypatch.setattr(main, "load_options_file", Mock(return_value=config))
    monkeypatch.setattr(main, "configure_logging", Mock())
    monkeypatch.setattr(main, "_publish_offline_if_no_cached_state", Mock())
    monkeypatch.setattr(main.time, "sleep", sleep)

    with pytest.raises(KeyboardInterrupt):
        main.main()

    sleep.assert_called_once_with(main.ERROR_RETRY_BACKOFF_SECONDS)


def test_run_once_raises_runtime_state_error_for_malformed_cached_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    options_path = tmp_path / "options.json"
    state_path = tmp_path / "state.json"
    state_path.write_text("{bad json", encoding="utf-8")

    monkeypatch.setattr(main, "load_options_file", Mock(return_value=app_config()))
    monkeypatch.setattr(main, "configure_logging", Mock())

    with pytest.raises(main.RuntimeStateError, match="cached accumulator state"):
        main.run_once(options_path, tmp_path)


def test_run_once_raises_runtime_state_error_for_structurally_invalid_cached_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    options_path = tmp_path / "options.json"
    state_path = tmp_path / "state.json"
    state_path.write_text('{"import_total_kwh": []}', encoding="utf-8")

    monkeypatch.setattr(main, "load_options_file", Mock(return_value=app_config()))
    monkeypatch.setattr(main, "configure_logging", Mock())

    with pytest.raises(main.RuntimeStateError, match="cached accumulator state"):
        main.run_once(options_path, tmp_path)


def test_run_once_rejects_existing_empty_cached_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    options_path = tmp_path / "options.json"
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(main, "load_options_file", Mock(return_value=app_config()))
    monkeypatch.setattr(main, "configure_logging", Mock())

    with pytest.raises(main.RuntimeStateError, match="not usable"):
        main.run_once(options_path, tmp_path)


def test_main_publishes_offline_after_malformed_cached_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = app_config()
    published_messages: list[list[MqttMessage]] = []

    class FakePublisher:
        def __init__(self, mqtt_config: MqttConfig) -> None:
            self.mqtt_config = mqtt_config

        def publish_messages(self, messages: list[MqttMessage]) -> None:
            published_messages.append(messages)

    monkeypatch.setattr(sys, "argv", ["prog", "--once", "--data-dir", str(tmp_path)])
    monkeypatch.setattr(
        main,
        "run_once",
        Mock(side_effect=main.RuntimeStateError("cached accumulator state could not be loaded")),
    )
    monkeypatch.setattr(main, "load_options_file", Mock(return_value=config))
    monkeypatch.setattr(main, "configure_logging", Mock())
    monkeypatch.setattr(main, "MqttPublisher", FakePublisher)
    monkeypatch.setattr(main.time, "sleep", Mock())

    main.main()

    assert published_messages == [
        [build_availability_message(config.mqtt, config.mprn, online=False)]
    ]
