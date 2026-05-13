from esbn_to_mqtt.logging import hash_mprn, mask_mprn, redact


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
