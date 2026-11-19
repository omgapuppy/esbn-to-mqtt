# esbn-to-mqtt/app/esbn_to_mqtt/statistics.py
from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from .models import StatisticsConfig

LOGGER = logging.getLogger(__name__)

SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"
CHUNK_SIZE = 1000
SOCKET_TIMEOUT_SECONDS = 30


class StatisticsError(RuntimeError):
    pass


@dataclass(frozen=True)
class HourlyStatistic:
    start: datetime  # UTC, top of the hour
    kwh: float  # energy used during this hour
    cumulative_kwh: float  # running total up to the end of this hour


# Collapse stored half-hour import values into complete UTC hours with a running total.
# An hour is only emitted once both of its half-hours are known, so a half-published
# hour never writes a partial value. The totals come from every interval the add-on has
# ever stored, so they stay stable when ESBN's download window rolls forward.
def build_hourly_import_statistics(
    interval_values: Mapping[str, float],
) -> list[HourlyStatistic]:
    halves: dict[datetime, dict[int, float]] = {}
    for key, value in interval_values.items():
        timestamp_text, _, channel = key.rpartition(":")
        if channel != "import":
            continue
        start = datetime.fromisoformat(timestamp_text).astimezone(UTC)
        hour = start.replace(minute=0, second=0, microsecond=0)
        halves.setdefault(hour, {})[start.minute] = value

    statistics: list[HourlyStatistic] = []
    cumulative = 0.0
    for hour in sorted(halves):
        parts = halves[hour]
        if 0 not in parts or 30 not in parts:
            continue
        kwh = parts[0] + parts[30]
        cumulative += kwh
        statistics.append(
            HourlyStatistic(
                start=hour,
                kwh=round(kwh, 6),
                cumulative_kwh=round(cumulative, 6),
            )
        )
    return statistics


# Build the recorder/import_statistics payload for one chunk of hours. The same
# cumulative figure is used for state and sum, matching an energy meter reading.
def _import_message(
    message_id: int,
    config: StatisticsConfig,
    chunk: Sequence[HourlyStatistic],
) -> dict[str, object]:
    return {
        "id": message_id,
        "type": "recorder/import_statistics",
        "metadata": {
            "has_sum": True,
            "mean_type": 0,
            "name": None,
            "source": config.source,
            "statistic_id": config.statistic_id,
            "unit_class": "energy",
            "unit_of_measurement": "kWh",
        },
        "stats": [
            {
                "start": item.start.isoformat(),
                "state": item.cumulative_kwh,
                "sum": item.cumulative_kwh,
            }
            for item in chunk
        ],
    }


def _receive(socket: object) -> dict[str, object]:
    raw = socket.recv(timeout=SOCKET_TIMEOUT_SECONDS)  # type: ignore[attr-defined]
    message = json.loads(raw)
    if not isinstance(message, dict):
        raise StatisticsError("unexpected message from Home Assistant")
    return message


# Push the hourly history to Home Assistant over the Supervisor websocket proxy.
# Re-sending an hour replaces it, so repeated polls never duplicate data.
def import_hourly_statistics(
    statistics: Sequence[HourlyStatistic],
    config: StatisticsConfig,
    *,
    url: str = SUPERVISOR_WS_URL,
    token: str | None = None,
) -> int:
    if not statistics:
        return 0
    access_token = token or os.environ.get("SUPERVISOR_TOKEN")
    if not access_token:
        raise StatisticsError("SUPERVISOR_TOKEN is not set; homeassistant_api access is required")

    try:
        with connect(url, open_timeout=SOCKET_TIMEOUT_SECONDS) as socket:
            greeting = _receive(socket)
            if greeting.get("type") != "auth_required":
                raise StatisticsError("Home Assistant did not request authentication")
            socket.send(json.dumps({"type": "auth", "access_token": access_token}))
            if _receive(socket).get("type") != "auth_ok":
                raise StatisticsError("Home Assistant rejected the add-on token")

            for number, offset in enumerate(range(0, len(statistics), CHUNK_SIZE), start=1):
                chunk = statistics[offset : offset + CHUNK_SIZE]
                socket.send(json.dumps(_import_message(number, config, chunk)))
                while True:
                    reply = _receive(socket)
                    if reply.get("id") == number and reply.get("type") == "result":
                        break
                if reply.get("success") is not True:
                    error = reply.get("error")
                    detail = error.get("message") if isinstance(error, dict) else error
                    raise StatisticsError(f"Home Assistant refused the import: {detail}")
    except (OSError, WebSocketException, ValueError) as exc:
        raise StatisticsError(f"could not reach Home Assistant: {exc}") from exc

    LOGGER.info(
        "imported %s hourly statistics into %s (latest hour %s)",
        len(statistics),
        config.statistic_id,
        statistics[-1].start.isoformat(),
    )
    return len(statistics)
