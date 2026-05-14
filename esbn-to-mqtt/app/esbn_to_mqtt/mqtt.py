from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from paho.mqtt.client import CallbackAPIVersion, Client

from .logging import hash_mprn
from .models import MeterTotals, MqttConfig

APP_NAME = "esbn_to_mqtt"
SOURCE_NAME = "esbn_to_mqtt"


@dataclass(frozen=True)
class MqttMessage:
    topic: str
    payload: dict[str, Any] | str
    retain: bool = True

    @property
    def encoded_payload(self) -> str:
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, sort_keys=True, separators=(",", ":"))


def _hashed_meter_id(mprn: str) -> str:
    return hash_mprn(mprn)


def state_topic(config: MqttConfig, mprn: str) -> str:
    return f"{config.topic_prefix}/{_hashed_meter_id(mprn)}/state"


def availability_topic(config: MqttConfig, mprn: str) -> str:
    return f"{config.topic_prefix}/{_hashed_meter_id(mprn)}/availability"


def _device_payload(mprn: str) -> dict[str, Any]:
    meter_id = _hashed_meter_id(mprn)
    return {
        "identifiers": [f"{APP_NAME}_{meter_id}"],
        "manufacturer": "ESB Networks",
        "model": "Smart Meter",
        "name": f"ESBN Meter {meter_id}",
    }


def _discovery_topic(config: MqttConfig, mprn: str, role: str) -> str:
    meter_id = _hashed_meter_id(mprn)
    return f"{config.discovery_prefix}/sensor/{APP_NAME}_{meter_id}/{role}/config"


def _discovery_payload(config: MqttConfig, mprn: str, role: str, name: str) -> dict[str, Any]:
    meter_id = _hashed_meter_id(mprn)
    return {
        "availability_topic": availability_topic(config, mprn),
        "device": _device_payload(mprn),
        "device_class": "energy",
        "name": name,
        "object_id": f"{APP_NAME}_{meter_id}_{role}",
        "state_class": "total_increasing",
        "state_topic": state_topic(config, mprn),
        "suggested_display_precision": 3,
        "unique_id": f"{APP_NAME}_{meter_id}_{role}",
        "unit_of_measurement": "kWh",
        "value_template": f"{{{{ value_json.{role}_kwh }}}}",
    }


def build_discovery_messages(
    config: MqttConfig, mprn: str, *, include_export: bool
) -> list[MqttMessage]:
    messages = [
        MqttMessage(
            topic=_discovery_topic(config, mprn, "import_total"),
            payload=_discovery_payload(config, mprn, "import_total", "ESBN Import Total"),
        )
    ]
    if include_export:
        messages.append(
            MqttMessage(
                topic=_discovery_topic(config, mprn, "export_total"),
                payload=_discovery_payload(config, mprn, "export_total", "ESBN Export Total"),
            )
        )
    return messages


def build_state_message(config: MqttConfig, mprn: str, totals: MeterTotals) -> MqttMessage:
    payload: dict[str, Any] = {
        "import_total_kwh": totals.import_total_kwh,
        "last_successful_fetch": datetime.now(UTC).isoformat(),
        "source": SOURCE_NAME,
    }
    if totals.export_total_kwh is not None:
        payload["export_total_kwh"] = totals.export_total_kwh
    if totals.last_interval_start is not None:
        payload["last_interval_start"] = totals.last_interval_start.isoformat()
    return MqttMessage(topic=state_topic(config, mprn), payload=payload)


class MqttPublisher:
    def __init__(self, config: MqttConfig) -> None:
        self._config = config
        self._client = Client(callback_api_version=CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(config.username, config.password)

    def publish_messages(self, messages: list[MqttMessage]) -> None:
        self._client.connect(self._config.host, self._config.port)
        try:
            for message in messages:
                publish_result = self._client.publish(
                    message.topic,
                    payload=message.encoded_payload,
                    qos=1,
                    retain=message.retain,
                )
                publish_result.wait_for_publish()
        finally:
            self._client.disconnect()
