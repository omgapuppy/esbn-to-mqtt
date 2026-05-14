from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from esbn_to_mqtt.logging import hash_mprn
from esbn_to_mqtt.models import MeterTotals, MqttConfig
from esbn_to_mqtt.mqtt import (
    MqttMessage,
    MqttPublisher,
    MqttPublishError,
    build_availability_message,
    build_discovery_messages,
    build_state_message,
)


def mqtt_config() -> MqttConfig:
    return MqttConfig(
        host="core-mosquitto",
        port=1883,
        username="ha",
        password="secret",
    )


def totals() -> MeterTotals:
    return MeterTotals(
        import_total_kwh=3.45,
        export_total_kwh=1.25,
        last_interval_start=datetime(2026, 5, 12, 1, 30, tzinfo=UTC),
    )


def test_build_discovery_messages_use_energy_dashboard_metadata() -> None:
    messages = build_discovery_messages(mqtt_config(), "10000000000", include_export=True)
    import_message = next(message for message in messages if "import_total" in message.topic)
    last_update_message = next(message for message in messages if "last_update" in message.topic)
    meter_id = hash_mprn("10000000000")

    assert import_message.retain is True
    assert import_message.payload["device_class"] == "energy"
    assert import_message.payload["state_class"] == "total_increasing"
    assert import_message.payload["unit_of_measurement"] == "kWh"
    assert import_message.payload["availability_topic"].endswith("/availability")
    assert "10000000000" not in str(import_message.payload)
    assert last_update_message.retain is True
    assert last_update_message.topic == (
        f"homeassistant/sensor/esbn_to_mqtt_{meter_id}/last_update/config"
    )
    assert (
        last_update_message.payload["availability_topic"]
        == import_message.payload["availability_topic"]
    )
    assert last_update_message.payload["state_topic"] == import_message.payload["state_topic"]
    assert last_update_message.payload["device"] == import_message.payload["device"]
    assert last_update_message.payload["object_id"] == f"esbn_to_mqtt_{meter_id}_last_update"
    assert last_update_message.payload["unique_id"] == f"esbn_to_mqtt_{meter_id}_last_update"
    assert last_update_message.payload["value_template"] == "{{ value_json.last_successful_fetch }}"
    assert "device_class" not in last_update_message.payload
    assert "state_class" not in last_update_message.payload
    assert "unit_of_measurement" not in last_update_message.payload
    assert "10000000000" not in str(last_update_message.payload)


def test_build_state_message_contains_totals_and_timestamps() -> None:
    message = build_state_message(mqtt_config(), "10000000000", totals())

    assert message.retain is True
    assert message.payload["import_total_kwh"] == 3.45
    assert message.payload["export_total_kwh"] == 1.25
    assert message.payload["last_interval_start"] == "2026-05-12T01:30:00+00:00"
    assert message.payload["source"] == "esb_networks_hdf_30_min_kwh"
    assert "last_successful_fetch" in message.payload
    assert datetime.fromisoformat(message.payload["last_successful_fetch"])


def test_build_availability_message_uses_retained_online_and_offline_payloads() -> None:
    online_message = build_availability_message(mqtt_config(), "10000000000", online=True)
    offline_message = build_availability_message(mqtt_config(), "10000000000", online=False)

    assert online_message.topic.endswith("/availability")
    assert online_message.retain is True
    assert online_message.payload == "online"
    assert offline_message.topic == online_message.topic
    assert offline_message.retain is True
    assert offline_message.payload == "offline"


def test_mqtt_publisher_starts_loop_before_publish_and_cleans_up() -> None:
    client = Mock()
    client.publish.return_value = SimpleNamespace(rc=0, wait_for_publish=Mock())
    publisher = MqttPublisher(mqtt_config(), client=client)
    message = MqttMessage(topic="test/topic", payload="payload")

    publisher.publish_messages([message])

    client.username_pw_set.assert_called_once_with("ha", "secret")
    client.connect.assert_called_once_with("core-mosquitto", 1883)
    client.loop_start.assert_called_once_with()
    client.publish.assert_called_once_with("test/topic", payload="payload", qos=1, retain=True)
    client.publish.return_value.wait_for_publish.assert_called_once_with()
    client.loop_stop.assert_called_once_with()
    client.disconnect.assert_called_once_with()


def test_mqtt_publisher_raises_on_publish_failure_after_connecting() -> None:
    client = Mock()
    client.publish.return_value = SimpleNamespace(rc=1, wait_for_publish=Mock())
    publisher = MqttPublisher(mqtt_config(), client=client)

    try:
        publisher.publish_messages([MqttMessage(topic="test/topic", payload="payload")])
    except MqttPublishError as exc:
        assert "rc=1" in str(exc)
    else:
        raise AssertionError("Expected MqttPublishError")

    client.loop_start.assert_called_once_with()
    client.publish.return_value.wait_for_publish.assert_not_called()
    client.loop_stop.assert_called_once_with()
    client.disconnect.assert_called_once_with()
