from __future__ import annotations

import hashlib
import logging

LOG_LEVELS: dict[str, int] = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
}


def mask_mprn(mprn: str) -> str:
    if len(mprn) <= 3:
        return "*" * len(mprn)
    return "*" * (len(mprn) - 3) + mprn[-3:]


def hash_mprn(mprn: str) -> str:
    return hashlib.sha256(mprn.encode("utf-8")).hexdigest()[:12]


def redact(message: str, secrets: list[str]) -> str:
    redacted = message
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def level_name_to_logging_level(level: str) -> int:
    return LOG_LEVELS[level.strip().lower()]


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level_name_to_logging_level(level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
