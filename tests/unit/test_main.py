from __future__ import annotations

import sys
from unittest.mock import Mock

import pytest
from esbn_to_mqtt import main
from esbn_to_mqtt.esbn import EsbnError
from esbn_to_mqtt.models import AppConfig, EsbnCredentials, MqttConfig
from esbn_to_mqtt.mqtt import MqttMessage, MqttPublishError, build_availability_message


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
) -> None:
    config = app_config()
    published_messages: list[list[MqttMessage]] = []

    class FakePublisher:
        def __init__(self, mqtt_config: MqttConfig) -> None:
            self.mqtt_config = mqtt_config

        def publish_messages(self, messages: list[MqttMessage]) -> None:
            published_messages.append(messages)

    monkeypatch.setattr(sys, "argv", ["prog", "--once"])
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
def test_main_publishes_offline_availability_after_runtime_error_when_config_loads(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    config = app_config()
    published_messages: list[list[MqttMessage]] = []

    class FakePublisher:
        def __init__(self, mqtt_config: MqttConfig) -> None:
            self.mqtt_config = mqtt_config

        def publish_messages(self, messages: list[MqttMessage]) -> None:
            published_messages.append(messages)

    monkeypatch.setattr(sys, "argv", ["prog", "--once"])
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
