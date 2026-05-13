import pytest

from esbn_to_mqtt.config import AppConfig, ConfigError, load_config_dict


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
