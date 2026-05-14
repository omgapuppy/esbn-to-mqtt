from pathlib import Path

from esbn_to_mqtt.hdf import parse_hdf_csv
from esbn_to_mqtt.models import MqttConfig
from esbn_to_mqtt.mqtt import build_discovery_messages, build_state_message
from esbn_to_mqtt.state import AccumulatorState


def test_fixture_to_mqtt_messages_pipeline() -> None:
    content = Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text()
    readings = parse_hdf_csv(content)
    totals = AccumulatorState.empty().apply(readings).to_totals()
    mqtt_config = MqttConfig(
        host="core-mosquitto",
        port=1883,
        username="ha",
        password="secret",
    )

    discovery = build_discovery_messages(mqtt_config, "10000000000", include_export=True)
    state = build_state_message(mqtt_config, "10000000000", totals)

    assert len(discovery) == 3
    assert state.payload["import_total_kwh"] == 0.45
    assert state.payload["export_total_kwh"] == 0.03
