from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .captcha import build_captcha_solver
from .config import load_options_file
from .esbn import EsbnChallengeError, EsbnClient, EsbnError
from .hdf import HdfParseError, parse_hdf_csv
from .logging import configure_logging, mask_mprn, redact
from .metrics import build_meter_metrics
from .models import AppConfig
from .mqtt import (
    MqttPublisher,
    MqttPublishError,
    build_availability_message,
    build_discovery_messages,
    build_state_message,
)
from .state import AccumulatorState

LOGGER = logging.getLogger(__name__)
ERROR_RETRY_BACKOFF_SECONDS = 15 * 60
ESBN_COOKIE_FILE = "esbn-cookies.txt"
ESBN_CHALLENGE_FILE = "esbn-challenge.json"


class RuntimeStateError(RuntimeError):
    pass


def _state_has_totals(state: AccumulatorState) -> bool:
    return state.last_interval_start is not None and bool(state.processed_intervals)


def _redaction_secrets(config: AppConfig) -> list[str]:
    return [
        config.esbn.username,
        config.esbn.password,
        config.esbn.mprn,
        config.mqtt.username,
        config.mqtt.password,
    ]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _challenge_path(data_dir: Path) -> Path:
    return data_dir / ESBN_CHALLENGE_FILE


def _cookie_jar_path(data_dir: Path) -> Path:
    return data_dir / ESBN_COOKIE_FILE


def _read_challenged_at(path: Path) -> datetime | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None

    challenged_at = data.get("challenged_at")
    if not isinstance(challenged_at, str):
        return None

    try:
        parsed = datetime.fromisoformat(challenged_at)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _clear_challenge_cooldown(data_dir: Path) -> None:
    try:
        _challenge_path(data_dir).unlink()
    except FileNotFoundError:
        return


def _record_challenge_cooldown(data_dir: Path) -> None:
    path = _challenge_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"challenged_at": _utc_now().isoformat()}),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _raise_if_challenge_cooldown_active(config: AppConfig, data_dir: Path) -> None:
    path = _challenge_path(data_dir)
    if config.captcha.solver != "disabled":
        _clear_challenge_cooldown(data_dir)
        return

    challenged_at = _read_challenged_at(path)
    if challenged_at is None:
        _clear_challenge_cooldown(data_dir)
        return

    retry_at = challenged_at + timedelta(seconds=config.poll_interval_seconds)
    now = _utc_now()
    if now >= retry_at:
        _clear_challenge_cooldown(data_dir)
        return

    retry_after_seconds = max(1, int((retry_at - now).total_seconds()))
    raise EsbnChallengeError(
        "ESBN requested browser verification; automated login paused until next poll",
        retry_after_seconds=retry_after_seconds,
    )


def run_once(options_path: Path, data_dir: Path) -> AppConfig:
    config = load_options_file(options_path)
    configure_logging(config.log_level)
    LOGGER.info("starting esbn-to-mqtt for MPRN %s", mask_mprn(config.mprn))
    publisher = MqttPublisher(config.mqtt)
    try:
        publisher.check_connection()
    except MqttPublishError:
        LOGGER.error(
            "MQTT connection check failed for %s:%s",
            config.mqtt.host,
            config.mqtt.port,
        )
        raise
    LOGGER.info("MQTT connection check succeeded for %s:%s", config.mqtt.host, config.mqtt.port)

    _raise_if_challenge_cooldown_active(config, data_dir)
    captcha_solver = build_captcha_solver(config.captcha)
    if captcha_solver is not None:
        LOGGER.info("CAPTCHA solver configured; ESBN challenges will be submitted to 2Captcha")

    state_path = data_dir / "state.json"
    state_exists = state_path.exists()
    try:
        accumulator = AccumulatorState.load(state_path)
    except (OSError, ValueError) as exc:
        raise RuntimeStateError("cached accumulator state could not be loaded") from exc
    if state_exists and not _state_has_totals(accumulator):
        raise RuntimeStateError("cached accumulator state was not usable")
    client = EsbnClient(
        config.esbn,
        cookie_jar_path=_cookie_jar_path(data_dir),
        captcha_solver=captcha_solver,
    )

    try:
        csv_content = client.download_30_min_kwh_hdf()
        readings = parse_hdf_csv(csv_content)
        processed_before = accumulator.processed_intervals
        accumulator = accumulator.apply(readings)
        accumulator.save(state_path)

        totals = accumulator.to_totals()
        metrics = build_meter_metrics(
            readings,
            processed_before=processed_before,
            processed_after=totals.processed_intervals,
            auth_path=client.last_auth_path,
            captcha_used=client.captcha_used,
            now=_utc_now(),
        )
        messages = build_discovery_messages(
            config.mqtt,
            config.mprn,
            include_export=totals.export_total_kwh is not None,
        )
        messages.append(build_state_message(config.mqtt, config.mprn, totals, metrics))
        messages.append(build_availability_message(config.mqtt, config.mprn, online=True))
        publisher.publish_messages(messages)
        _clear_challenge_cooldown(data_dir)
    finally:
        client.close()

    return config


def _has_usable_cached_state(data_dir: Path) -> bool:
    try:
        state = AccumulatorState.load(data_dir / "state.json")
    except (OSError, ValueError):
        return False
    return _state_has_totals(state)


def _publish_offline_if_no_cached_state(config: AppConfig, data_dir: Path) -> None:
    if _has_usable_cached_state(data_dir):
        LOGGER.warning("polling failed; keeping last known MQTT state available")
        return

    publisher = MqttPublisher(config.mqtt)
    publisher.publish_messages(
        [build_availability_message(config.mqtt, config.mprn, online=False)]
    )


def _retry_sleep_seconds(exc: Exception, config: AppConfig) -> int:
    if isinstance(exc, EsbnChallengeError):
        if exc.retry_after_seconds is not None:
            return exc.retry_after_seconds
        return config.poll_interval_seconds
    return min(config.poll_interval_seconds, ERROR_RETRY_BACKOFF_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    while True:
        sleep_seconds = 0
        try:
            config = run_once(args.options, args.data_dir)
        except (EsbnError, HdfParseError, MqttPublishError, RuntimeStateError) as exc:
            config = load_options_file(args.options)
            configure_logging(config.log_level)
            if (
                isinstance(exc, EsbnChallengeError)
                and exc.retry_after_seconds is None
            ):
                _record_challenge_cooldown(args.data_dir)
            LOGGER.error(
                "polling cycle failed: %s",
                redact(str(exc), _redaction_secrets(config)),
            )
            try:
                _publish_offline_if_no_cached_state(config, args.data_dir)
            except MqttPublishError as publish_exc:
                LOGGER.error(
                    "failed to publish offline availability: %s",
                    redact(str(publish_exc), _redaction_secrets(config)),
                )
            if args.once:
                break
            sleep_seconds = _retry_sleep_seconds(exc, config)
        else:
            if args.once:
                break
            sleep_seconds = config.poll_interval_seconds
            LOGGER.info("polling cycle completed; sleeping for %s seconds", sleep_seconds)

        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
