from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .logging import LOG_LEVELS
from .models import AppConfig, CaptchaConfig, EsbnCredentials, MqttConfig

MPRN_PATTERN = re.compile(r"^\d{11}$")


class ConfigError(ValueError):
    pass


def _required_str(options: dict[str, Any], key: str) -> str:
    value = options.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} is required")
    return value.strip()


def _optional_str(options: dict[str, Any], key: str) -> str | None:
    value = options.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    stripped = value.strip()
    return stripped if stripped else None


def _required_int(options: dict[str, Any], key: str) -> int:
    value = options.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def _optional_int(options: dict[str, Any], key: str, default: int) -> int:
    value = options.get(key, default)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    integer_value: int = value
    return integer_value


def _env_int(key: str, default: str) -> int:
    value = os.environ.get(key, default)
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer") from exc


def _log_level(options: dict[str, Any]) -> str:
    value = _required_str(options, "log_level").lower()
    if value not in LOG_LEVELS:
        supported_levels = ", ".join(LOG_LEVELS)
        raise ConfigError(f"log_level must be one of: {supported_levels}")
    return value


def _captcha_config(options: dict[str, Any]) -> CaptchaConfig:
    solver = _optional_str(options, "captcha_solver") or "disabled"
    if solver not in {"disabled", "2captcha"}:
        raise ConfigError("captcha_solver must be one of: disabled, 2captcha")

    timeout_seconds = _optional_int(options, "two_captcha_timeout_seconds", 120)
    if timeout_seconds < 30 or timeout_seconds > 600:
        raise ConfigError("two_captcha_timeout_seconds must be between 30 and 600")

    api_key = _optional_str(options, "two_captcha_api_key")
    if solver == "2captcha" and api_key is None:
        raise ConfigError("two_captcha_api_key is required when captcha_solver is 2captcha")

    return CaptchaConfig(
        solver=solver,
        two_captcha_api_key=api_key,
        two_captcha_timeout_seconds=timeout_seconds,
    )


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
        captcha=_captcha_config(options),
        poll_interval_hours=poll_interval_hours,
        log_level=_log_level(options),
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
            "mqtt_port": _env_int("MQTT_PORT", "1883"),
            "mqtt_username": os.environ.get("MQTT_USERNAME", ""),
            "mqtt_password": os.environ.get("MQTT_PASSWORD", ""),
            "poll_interval_hours": _env_int("POLL_INTERVAL_HOURS", "6"),
            "mqtt_discovery_prefix": os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant"),
            "mqtt_topic_prefix": os.environ.get("MQTT_TOPIC_PREFIX", "esbn_to_mqtt"),
            "captcha_solver": os.environ.get("CAPTCHA_SOLVER", "disabled"),
            "two_captcha_api_key": os.environ.get("TWO_CAPTCHA_API_KEY"),
            "two_captcha_timeout_seconds": _env_int("TWO_CAPTCHA_TIMEOUT_SECONDS", "120"),
            "log_level": os.environ.get("LOG_LEVEL", "info"),
        }
    )
