from __future__ import annotations

import hashlib
import logging


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


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
