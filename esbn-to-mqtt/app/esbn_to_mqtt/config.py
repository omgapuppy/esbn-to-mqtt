from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .models import AppConfig, EsbnCredentials, MqttConfig

MPRN_PATTERN = re.compile(r"^\d{11}$")


class ConfigError(ValueError):
    pass


def _required_str(options: dict[str, Any], key: str) -> str:
    value = options.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} is required")
    return value.strip()


def _required_int(options: dict[str, Any], key: str) -> int:
    value = options.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def load_config_dict(options: dict[str, Any]) -> AppConfig:
    try:
        mprn = _required_str(options, "mprn")
    except ConfigError as exc:
        raise ConfigError("MPRN is required") from exc
    if not MPRN_PATTERN.match(mprn):
        raise ConfigError("MPRN must be exactly 11 digits")

    poll_interval_hours = _required_int(options, "poll_interval_hours")
    if poll_interval_hours < 1:
        raise ConfigError("poll_interval_hours must be at least 1")

    mqtt_port = _required_int(options, "mqtt_port")
    if mqtt_port < 1 or mqtt_port > 65535:
        raise ConfigError("mqtt_port must be a valid TCP port")

    return AppConfig(
        esbn=EsbnCredentials(
            username=_required_str(options, "esbn_username"),
            password=_required_str(options, "esbn_password"),
            mprn=mprn,
        ),
        mqtt=MqttConfig(
            host=_required_str(options, "mqtt_host"),
            port=mqtt_port,
            username=_required_str(options, "mqtt_username"),
            password=_required_str(options, "mqtt_password"),
            discovery_prefix=_required_str(options, "mqtt_discovery_prefix"),
            topic_prefix=_required_str(options, "mqtt_topic_prefix"),
        ),
        poll_interval_hours=poll_interval_hours,
        log_level=_required_str(options, "log_level"),
    )


def load_options_file(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as handle:
        options = json.load(handle)
    if not isinstance(options, dict):
        raise ConfigError("options file must contain a JSON object")
    return load_config_dict(options)


def load_env_config() -> AppConfig:
    return load_config_dict(
        {
            "esbn_username": os.environ.get("ESBN_USERNAME", ""),
            "esbn_password": os.environ.get("ESBN_PASSWORD", ""),
            "mprn": os.environ.get("ESBN_MPRN", ""),
            "mqtt_host": os.environ.get("MQTT_HOST", "core-mosquitto"),
            "mqtt_port": int(os.environ.get("MQTT_PORT", "1883")),
            "mqtt_username": os.environ.get("MQTT_USERNAME", ""),
            "mqtt_password": os.environ.get("MQTT_PASSWORD", ""),
            "poll_interval_hours": int(os.environ.get("POLL_INTERVAL_HOURS", "6")),
            "mqtt_discovery_prefix": os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant"),
            "mqtt_topic_prefix": os.environ.get("MQTT_TOPIC_PREFIX", "esbn_to_mqtt"),
            "log_level": os.environ.get("LOG_LEVEL", "info"),
        }
    )
