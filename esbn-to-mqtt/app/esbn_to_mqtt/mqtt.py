from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from typing import Any, cast

from paho.mqtt.client import Client
from paho.mqtt.enums import CallbackAPIVersion

from .logging import hash_mprn
from .models import MeterMetrics, MeterTotals, MqttConfig

APP_NAME = "esbn_to_mqtt"
SOURCE_NAME = "esb_networks_hdf_30_min_kwh"
AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"
MQTT_CONNECT_TIMEOUT_SECONDS = 10.0


class MqttPublishError(RuntimeError):
    pass


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


def build_availability_message(config: MqttConfig, mprn: str, *, online: bool) -> MqttMessage:
    return MqttMessage(
        topic=availability_topic(config, mprn),
        payload=AVAILABILITY_ONLINE if online else AVAILABILITY_OFFLINE,
    )


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


def _sensor_discovery_payload(
    config: MqttConfig,
    mprn: str,
    role: str,
    name: str,
    value_key: str,
    *,
    device_class: str | None = None,
    state_class: str | None = None,
    unit_of_measurement: str | None = None,
    entity_category: str | None = None,
    suggested_display_precision: int | None = None,
) -> dict[str, Any]:
    meter_id = _hashed_meter_id(mprn)
    payload: dict[str, Any] = {
        "availability_topic": availability_topic(config, mprn),
        "device": _device_payload(mprn),
        "name": name,
        "object_id": f"{APP_NAME}_{meter_id}_{role}",
        "state_topic": state_topic(config, mprn),
        "unique_id": f"{APP_NAME}_{meter_id}_{role}",
        "value_template": f"{{{{ value_json.{value_key} }}}}",
    }
    if device_class is not None:
        payload["device_class"] = device_class
    if state_class is not None:
        payload["state_class"] = state_class
    if unit_of_measurement is not None:
        payload["unit_of_measurement"] = unit_of_measurement
    if entity_category is not None:
        payload["entity_category"] = entity_category
    if suggested_display_precision is not None:
        payload["suggested_display_precision"] = suggested_display_precision
    return payload


def _energy_discovery_payload(
    config: MqttConfig,
    mprn: str,
    role: str,
    name: str,
    value_key: str,
    *,
    state_class: str,
) -> dict[str, Any]:
    return _sensor_discovery_payload(
        config,
        mprn,
        role,
        name,
        value_key,
        device_class="energy",
        state_class=state_class,
        unit_of_measurement="kWh",
        suggested_display_precision=3,
    )


def _last_update_discovery_payload(config: MqttConfig, mprn: str) -> dict[str, Any]:
    meter_id = _hashed_meter_id(mprn)
    return {
        "availability_topic": availability_topic(config, mprn),
        "device": _device_payload(mprn),
        "name": "ESBN Last Update",
        "object_id": f"{APP_NAME}_{meter_id}_last_update",
        "state_topic": state_topic(config, mprn),
        "unique_id": f"{APP_NAME}_{meter_id}_last_update",
        "value_template": "{{ value_json.last_successful_fetch }}",
    }


def build_discovery_messages(
    config: MqttConfig,
    mprn: str,
    *,
    include_export: bool,
    include_tariff: bool = False,
    tariff_currency: str = "EUR",
) -> list[MqttMessage]:
    messages = [
        MqttMessage(
            topic=_discovery_topic(config, mprn, "import_total"),
            payload=_energy_discovery_payload(
                config,
                mprn,
                "import_total",
                "ESBN Import Total",
                "import_total_kwh",
                state_class="total_increasing",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "latest_import_interval"),
            payload=_energy_discovery_payload(
                config,
                mprn,
                "latest_import_interval",
                "ESBN Latest Interval Import",
                "latest_import_interval_kwh",
                state_class="measurement",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "today_import"),
            payload=_energy_discovery_payload(
                config,
                mprn,
                "today_import",
                "ESBN Today Import",
                "today_import_kwh",
                state_class="total",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "current_month_import"),
            payload=_energy_discovery_payload(
                config,
                mprn,
                "current_month_import",
                "ESBN Current Month Import",
                "current_month_import_kwh",
                state_class="total",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "last_update"),
            payload=_last_update_discovery_payload(config, mprn),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "latest_interval_start"),
            payload=_sensor_discovery_payload(
                config,
                mprn,
                "latest_interval_start",
                "ESBN Latest Interval Start",
                "latest_esbn_interval_start",
                entity_category="diagnostic",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "data_lag"),
            payload=_sensor_discovery_payload(
                config,
                mprn,
                "data_lag",
                "ESBN Data Lag",
                "data_lag_hours",
                device_class="duration",
                state_class="measurement",
                unit_of_measurement="h",
                entity_category="diagnostic",
                suggested_display_precision=2,
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "new_interval_values_processed"),
            payload=_sensor_discovery_payload(
                config,
                mprn,
                "new_interval_values_processed",
                "ESBN New Values Processed",
                "new_interval_values_processed",
                state_class="measurement",
                entity_category="diagnostic",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "hdf_rows_parsed"),
            payload=_sensor_discovery_payload(
                config,
                mprn,
                "hdf_rows_parsed",
                "ESBN HDF Rows Parsed",
                "hdf_rows_parsed",
                state_class="measurement",
                entity_category="diagnostic",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "captcha_used"),
            payload=_sensor_discovery_payload(
                config,
                mprn,
                "captcha_used",
                "ESBN CAPTCHA Used",
                "captcha_used",
                entity_category="diagnostic",
            ),
        ),
        MqttMessage(
            topic=_discovery_topic(config, mprn, "auth_path"),
            payload=_sensor_discovery_payload(
                config,
                mprn,
                "auth_path",
                "ESBN Auth Path",
                "auth_path",
                entity_category="diagnostic",
            ),
        ),
    ]
    if include_export:
        messages.extend(
            [
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "export_total"),
                    payload=_energy_discovery_payload(
                        config,
                        mprn,
                        "export_total",
                        "ESBN Export Total",
                        "export_total_kwh",
                        state_class="total_increasing",
                    ),
                ),
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "latest_export_interval"),
                    payload=_energy_discovery_payload(
                        config,
                        mprn,
                        "latest_export_interval",
                        "ESBN Latest Interval Export",
                        "latest_export_interval_kwh",
                        state_class="measurement",
                    ),
                ),
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "today_export"),
                    payload=_energy_discovery_payload(
                        config,
                        mprn,
                        "today_export",
                        "ESBN Today Export",
                        "today_export_kwh",
                        state_class="total",
                    ),
                ),
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "current_month_export"),
                    payload=_energy_discovery_payload(
                        config,
                        mprn,
                        "current_month_export",
                        "ESBN Current Month Export",
                        "current_month_export_kwh",
                        state_class="total",
                    ),
                ),
            ]
        )
    if include_tariff:
        messages.extend(
            [
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "import_cost_total"),
                    payload=_sensor_discovery_payload(
                        config,
                        mprn,
                        "import_cost_total",
                        "ESBN Import Cost Total",
                        "import_cost_total",
                        device_class="monetary",
                        state_class="total_increasing",
                        unit_of_measurement=tariff_currency,
                        suggested_display_precision=2,
                    ),
                ),
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "today_import_cost"),
                    payload=_sensor_discovery_payload(
                        config,
                        mprn,
                        "today_import_cost",
                        "ESBN Today Import Cost",
                        "today_import_cost",
                        device_class="monetary",
                        state_class="total",
                        unit_of_measurement=tariff_currency,
                        suggested_display_precision=2,
                    ),
                ),
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "current_month_import_cost"),
                    payload=_sensor_discovery_payload(
                        config,
                        mprn,
                        "current_month_import_cost",
                        "ESBN Current Month Import Cost",
                        "current_month_import_cost",
                        device_class="monetary",
                        state_class="total",
                        unit_of_measurement=tariff_currency,
                        suggested_display_precision=2,
                    ),
                ),
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "current_tariff"),
                    payload=_sensor_discovery_payload(
                        config,
                        mprn,
                        "current_tariff",
                        "ESBN Current Tariff",
                        "current_tariff",
                    ),
                ),
                MqttMessage(
                    topic=_discovery_topic(config, mprn, "current_tariff_rate"),
                    payload=_sensor_discovery_payload(
                        config,
                        mprn,
                        "current_tariff_rate",
                        "ESBN Current Tariff Rate",
                        "current_tariff_rate",
                        state_class="measurement",
                        unit_of_measurement=f"{tariff_currency}/kWh",
                        suggested_display_precision=4,
                    ),
                ),
            ]
        )
    return messages


def build_state_message(
    config: MqttConfig,
    mprn: str,
    totals: MeterTotals,
    metrics: MeterMetrics | None = None,
) -> MqttMessage:
    payload: dict[str, Any] = {
        "import_total_kwh": totals.import_total_kwh,
        "import_cost_total": totals.import_cost_total,
        "last_successful_fetch": datetime.now(UTC).isoformat(),
        "source": SOURCE_NAME,
    }
    if totals.export_total_kwh is not None:
        payload["export_total_kwh"] = totals.export_total_kwh
    if totals.last_interval_start is not None:
        payload["last_interval_start"] = totals.last_interval_start.isoformat()
    if metrics is not None:
        payload.update(
            {
                "latest_import_interval_kwh": metrics.latest_import_interval_kwh,
                "today_import_kwh": metrics.today_import_kwh,
                "current_month_import_kwh": metrics.current_month_import_kwh,
                "data_lag_hours": metrics.data_lag_hours,
                "hdf_rows_parsed": metrics.hdf_rows_parsed,
                "new_interval_values_processed": metrics.new_interval_values_processed,
                "captcha_used": metrics.captcha_used,
                "auth_path": metrics.auth_path,
            }
        )
        if metrics.today_import_cost is not None:
            payload["today_import_cost"] = metrics.today_import_cost
        if metrics.current_month_import_cost is not None:
            payload["current_month_import_cost"] = metrics.current_month_import_cost
        if metrics.current_tariff is not None:
            payload["current_tariff"] = metrics.current_tariff
        if metrics.current_tariff_rate is not None:
            payload["current_tariff_rate"] = metrics.current_tariff_rate
        if metrics.tariff_currency is not None:
            payload["tariff_currency"] = metrics.tariff_currency
        if metrics.latest_export_interval_kwh is not None:
            payload["latest_export_interval_kwh"] = metrics.latest_export_interval_kwh
        if metrics.today_export_kwh is not None:
            payload["today_export_kwh"] = metrics.today_export_kwh
        if metrics.current_month_export_kwh is not None:
            payload["current_month_export_kwh"] = metrics.current_month_export_kwh
        if metrics.latest_esbn_interval_start is not None:
            payload["latest_esbn_interval_start"] = (
                metrics.latest_esbn_interval_start.isoformat()
            )
    return MqttMessage(topic=state_topic(config, mprn), payload=payload)


def _reason_code_failed(reason_code: object) -> bool:
    is_failure = getattr(reason_code, "is_failure", None)
    if isinstance(is_failure, bool):
        return is_failure
    if callable(is_failure):
        failure_check = cast("Callable[[], object]", is_failure)
        return bool(failure_check())
    if isinstance(reason_code, int):
        return reason_code != 0
    if isinstance(reason_code, str):
        return reason_code.lower() != "success"
    return str(reason_code).lower() != "success"


class MqttPublisher:
    def __init__(self, config: MqttConfig, client: Client | None = None) -> None:
        self._config = config
        self._client = client or Client(callback_api_version=CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(config.username, config.password)

    def _connect(self) -> None:
        try:
            result_code = self._client.connect(self._config.host, self._config.port)
        except OSError as exc:
            raise MqttPublishError(
                f"Failed to connect to MQTT broker {self._config.host}:{self._config.port}"
            ) from exc
        if result_code != 0:
            raise MqttPublishError(
                "Failed to connect to MQTT broker "
                f"{self._config.host}:{self._config.port}: rc={result_code}"
            )

    def check_connection(self) -> None:
        connected = Event()
        reason_code: object | None = None
        previous_on_connect = self._client.on_connect

        def on_connect(
            client: Client,
            userdata: object,
            flags: object,
            rc: object,
            properties: object,
        ) -> None:
            nonlocal reason_code
            reason_code = rc
            connected.set()

        self._client.on_connect = on_connect
        loop_started = False
        connected_to_socket = False
        try:
            self._connect()
            connected_to_socket = True
            self._client.loop_start()
            loop_started = True
            if not connected.wait(MQTT_CONNECT_TIMEOUT_SECONDS):
                raise MqttPublishError(
                    "Timed out waiting for MQTT broker connection acknowledgement"
                )
            if _reason_code_failed(reason_code):
                raise MqttPublishError(
                    f"MQTT broker rejected connection: rc={reason_code}"
                )
        finally:
            if loop_started:
                self._client.loop_stop()
            if connected_to_socket:
                self._client.disconnect()
            self._client.on_connect = previous_on_connect

    def publish_messages(self, messages: list[MqttMessage]) -> None:
        self._connect()
        self._client.loop_start()
        try:
            for message in messages:
                publish_result = self._client.publish(
                    message.topic,
                    payload=message.encoded_payload,
                    qos=1,
                    retain=message.retain,
                )
                if publish_result.rc != 0:
                    raise MqttPublishError(
                        f"Failed to publish MQTT message to {message.topic}: rc={publish_result.rc}"
                    )
                publish_result.wait_for_publish()
        finally:
            self._client.loop_stop()
            self._client.disconnect()
