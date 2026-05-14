from datetime import UTC, datetime

from esbn_to_mqtt.models import MeterTotals, MqttConfig
from esbn_to_mqtt.mqtt import build_discovery_messages, build_state_message


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

    assert import_message.retain is True
    assert import_message.payload["device_class"] == "energy"
    assert import_message.payload["state_class"] == "total_increasing"
    assert import_message.payload["unit_of_measurement"] == "kWh"
    assert import_message.payload["availability_topic"].endswith("/availability")
    assert "10000000000" not in str(import_message.payload)


def test_build_state_message_contains_totals_and_timestamps() -> None:
    message = build_state_message(mqtt_config(), "10000000000", totals())
    assert message.retain is True
    assert message.payload["import_total_kwh"] == 3.45
    assert message.payload["export_total_kwh"] == 1.25
    assert message.payload["last_interval_start"] == "2026-05-12T01:30:00+00:00"
