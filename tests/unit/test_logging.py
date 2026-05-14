import logging

import pytest
from esbn_to_mqtt.logging import (
    configure_logging,
    hash_mprn,
    level_name_to_logging_level,
    mask_mprn,
    redact,
)


def test_mask_mprn_keeps_only_last_three_digits() -> None:
    assert mask_mprn("10000012345") == "********345"


def test_hash_mprn_is_stable_and_not_raw() -> None:
    value = hash_mprn("10000012345")
    assert value == hash_mprn("10000012345")
    assert "10000012345" not in value


def test_redact_removes_sensitive_values() -> None:
    message = redact(
        "login person@example.com password=secret mprn=10000012345 cookie=abcdef",
        secrets=["secret", "abcdef", "person@example.com", "10000012345"],
    )
    assert "secret" not in message
    assert "abcdef" not in message
    assert "person@example.com" not in message
    assert "10000012345" not in message


@pytest.mark.parametrize(
    ("level_name", "logging_level"),
    [
        ("trace", logging.DEBUG),
        ("debug", logging.DEBUG),
        ("notice", logging.INFO),
        ("fatal", logging.CRITICAL),
    ],
)
def test_level_name_to_logging_level_maps_home_assistant_levels(
    level_name: str,
    logging_level: int,
) -> None:
    assert level_name_to_logging_level(level_name) == logging_level


def test_configure_logging_suppresses_httpx_info_logs() -> None:
    logging.getLogger("httpx").setLevel(logging.NOTSET)

    configure_logging("info")

    assert logging.getLogger("httpx").level == logging.WARNING
