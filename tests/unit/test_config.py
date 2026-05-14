import pytest
from esbn_to_mqtt.config import AppConfig, ConfigError, load_config_dict, load_env_config


def valid_options() -> dict[str, object]:
    return {
        "esbn_username": "person@example.com",
        "esbn_password": "secret",
        "mprn": "10000000000",
        "mqtt_host": "core-mosquitto",
        "mqtt_port": 1883,
        "mqtt_username": "ha",
        "mqtt_password": "mqttpass",
        "poll_interval_hours": 6,
        "mqtt_discovery_prefix": "homeassistant",
        "mqtt_topic_prefix": "esbn_to_mqtt",
        "log_level": "info",
    }


def test_load_config_dict_accepts_valid_options() -> None:
    config = load_config_dict(valid_options())
    assert isinstance(config, AppConfig)
    assert config.mprn == "10000000000"
    assert config.mqtt.host == "core-mosquitto"
    assert config.poll_interval_seconds == 21600


@pytest.mark.parametrize("mprn", ["", "123", "1234567890a", "123456789012"])
def test_load_config_dict_rejects_invalid_mprn(mprn: str) -> None:
    options = valid_options()
    options["mprn"] = mprn
    with pytest.raises(ConfigError, match="MPRN"):
        load_config_dict(options)


def test_load_config_dict_rejects_missing_secret() -> None:
    options = valid_options()
    options["esbn_password"] = ""
    with pytest.raises(ConfigError, match="esbn_password"):
        load_config_dict(options)


def test_load_config_dict_rejects_invalid_log_level() -> None:
    options = valid_options()
    options["log_level"] = "verbose"
    with pytest.raises(ConfigError, match="log_level"):
        load_config_dict(options)


def test_load_env_config_rejects_invalid_log_level_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ESBN_USERNAME", "person@example.com")
    monkeypatch.setenv("ESBN_PASSWORD", "secret")
    monkeypatch.setenv("ESBN_MPRN", "10000000000")
    monkeypatch.setenv("MQTT_USERNAME", "ha")
    monkeypatch.setenv("MQTT_PASSWORD", "mqttpass")
    monkeypatch.setenv("LOG_LEVEL", "verbose")

    with pytest.raises(ConfigError, match="log_level"):
        load_env_config()


@pytest.mark.parametrize(
    ("env_key", "message"),
    [
        ("MQTT_PORT", "MQTT_PORT must be an integer"),
        ("POLL_INTERVAL_HOURS", "POLL_INTERVAL_HOURS must be an integer"),
    ],
)
def test_load_env_config_rejects_invalid_integer_env_values(
    monkeypatch: pytest.MonkeyPatch,
    env_key: str,
    message: str,
) -> None:
    monkeypatch.setenv("ESBN_USERNAME", "person@example.com")
    monkeypatch.setenv("ESBN_PASSWORD", "secret")
    monkeypatch.setenv("ESBN_MPRN", "10000000000")
    monkeypatch.setenv("MQTT_USERNAME", "ha")
    monkeypatch.setenv("MQTT_PASSWORD", "mqttpass")
    monkeypatch.setenv(env_key, "not-an-int")

    with pytest.raises(ConfigError, match=message):
        load_env_config()
