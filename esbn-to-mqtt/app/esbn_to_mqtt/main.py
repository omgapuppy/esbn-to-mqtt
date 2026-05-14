from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from .config import load_options_file
from .esbn import EsbnClient, EsbnError
from .hdf import parse_hdf_csv
from .logging import configure_logging, mask_mprn, redact
from .models import AppConfig
from .mqtt import (
    MqttPublisher,
    build_availability_message,
    build_discovery_messages,
    build_state_message,
)
from .state import AccumulatorState

LOGGER = logging.getLogger(__name__)


def run_once(options_path: Path, data_dir: Path) -> AppConfig:
    config = load_options_file(options_path)
    configure_logging(config.log_level)
    LOGGER.info("starting esbn-to-mqtt for MPRN %s", mask_mprn(config.mprn))

    state_path = data_dir / "state.json"
    accumulator = AccumulatorState.load(state_path)
    publisher = MqttPublisher(config.mqtt)
    client = EsbnClient(config.esbn)

    try:
        csv_content = client.download_30_min_kwh_hdf()
        readings = parse_hdf_csv(csv_content)
        accumulator = accumulator.apply(readings)
        accumulator.save(state_path)

        totals = accumulator.to_totals()
        messages = build_discovery_messages(
            config.mqtt,
            config.mprn,
            include_export=totals.export_total_kwh is not None,
        )
        messages.append(build_state_message(config.mqtt, config.mprn, totals))
        messages.append(build_availability_message(config.mqtt, config.mprn, online=True))
        publisher.publish_messages(messages)
    finally:
        client.close()

    return config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    while True:
        try:
            config = run_once(args.options, args.data_dir)
        except EsbnError as exc:
            config = load_options_file(args.options)
            configure_logging(config.log_level)
            LOGGER.error(
                "ESBN polling failed: %s",
                redact(
                    str(exc),
                    [config.esbn.username, config.esbn.password, config.esbn.mprn],
                ),
            )
            if args.once:
                break
        else:
            if args.once:
                break

        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    main()
