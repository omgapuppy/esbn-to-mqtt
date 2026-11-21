"""Import complete ESBN hours into Home Assistant Recorder."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import batched
from math import isclose, isfinite
from time import monotonic

from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from .models import MeterReading

LOGGER = logging.getLogger(__name__)
SUPERVISOR_WS_URL = "ws://supervisor/core/websocket"
SOCKET_TIMEOUT_SECONDS = 30
IMPORT_BATCH_SIZE = 1000
MAX_MESSAGE_BYTES = 16 * 1024 * 1024


class StatisticsError(RuntimeError):
    """Recorder could not be reached or its history could not be reconciled."""


def statistic_id(mprn: str) -> str:
    digest = hashlib.sha256(mprn.encode()).hexdigest()[:16]
    return f"esbn:grid_import_{digest}"


def hourly_import(readings: Sequence[MeterReading]) -> dict[datetime, float]:
    halves: dict[datetime, dict[int, float]] = {}
    for reading in readings:
        if reading.import_kwh is None:
            continue
        start = reading.timestamp.astimezone(UTC)
        if start.minute not in (0, 30) or start.second or start.microsecond:
            continue
        if not isfinite(reading.import_kwh) or reading.import_kwh < 0:
            raise StatisticsError("HDF contains an invalid import reading")
        hour = start.replace(minute=0)
        halves.setdefault(hour, {})[start.minute] = reading.import_kwh

    return {
        hour: parts[0] + parts[30]
        for hour, parts in halves.items()
        if 0 in parts and 30 in parts
    }


def plan_updates(
    hourly: Mapping[datetime, float], recorded: Mapping[datetime, float]
) -> list[tuple[datetime, float]]:
    """Reconcile cumulative sums against the nearest surviving Recorder baseline."""
    updates: list[tuple[datetime, float]] = []
    total = 0.0
    for hour in sorted(hourly.keys() | recorded.keys()):
        existing = recorded.get(hour)
        if hour not in hourly:
            # Once we start changing the history we need the actual ESBN value for
            # every affected Recorder row. An old sum could already reflect part of
            # an interrupted import, so its difference isn't a safe substitute.
            if updates:
                raise StatisticsError(
                    f"HDF is missing a previously imported hour at {hour.isoformat()}; "
                    "Recorder history was left unchanged"
                )
            assert existing is not None
            total = existing
            continue

        total = round(total + hourly[hour], 6)
        if existing is None or not isclose(existing, total, rel_tol=0, abs_tol=0.0000005):
            updates.append((hour, total))
        else:
            total = existing
    return updates


def _receive(
    socket: ClientConnection, timeout: float = SOCKET_TIMEOUT_SECONDS
) -> dict[str, object]:
    message = json.loads(socket.recv(timeout=timeout))
    if not isinstance(message, dict):
        raise StatisticsError("unexpected message from Home Assistant")
    return message


def _command(
    socket: ClientConnection, message_id: int, command: str, **fields: object
) -> object:
    socket.send(json.dumps({"id": message_id, "type": command, **fields}, allow_nan=False))
    deadline = monotonic() + SOCKET_TIMEOUT_SECONDS
    while (remaining := deadline - monotonic()) > 0:
        reply = _receive(socket, remaining)
        if reply.get("id") == message_id and reply.get("type") == "result":
            if reply.get("success") is not True:
                error = reply.get("error")
                code = error.get("code") if isinstance(error, dict) else None
                raise StatisticsError(f"Home Assistant rejected {command} ({code})")
            return reply.get("result")
    raise StatisticsError(f"Home Assistant timed out on {command}")


def _recorded_sums(socket: ClientConnection, identifier: str) -> dict[datetime, float]:
    # Read the whole statistic, including history outside the current HDF window.
    # That provides an anchor after a reinstall and detects later rows a stale
    # export cannot safely revise. Only requested fields come back per hour.
    result = _command(
        socket,
        1,
        "recorder/statistics_during_period",
        statistic_ids=[identifier],
        period="hour",
        start_time="1970-01-01T00:00:00+00:00",
        types=["sum"],
    )
    if not isinstance(result, dict) or not isinstance(rows := result.get(identifier, []), list):
        raise StatisticsError("invalid Recorder statistics response")

    recorded: dict[datetime, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise StatisticsError("invalid Recorder statistics row")
        start, total = row.get("start"), row.get("sum")
        if (
            not isinstance(start, int | float)
            or isinstance(start, bool)
            or not isfinite(start)
            or start % 3_600_000 != 0
            or not isinstance(total, int | float)
            or isinstance(total, bool)
            or not isfinite(total)
            or total < 0
        ):
            raise StatisticsError("invalid Recorder statistics row")
        # The Recorder WebSocket API returns Unix milliseconds.
        hour = datetime.fromtimestamp(start / 1000, UTC)
        if hour in recorded:
            raise StatisticsError("duplicate hour in Recorder statistics response")
        recorded[hour] = float(total)
    return recorded


def sync_hourly_import(
    readings: Sequence[MeterReading],
    mprn: str,
    *,
    url: str = SUPERVISOR_WS_URL,
    token: str | None = None,
) -> int:
    hourly = hourly_import(readings)
    if not hourly:
        return 0

    access_token = token or os.environ.get("SUPERVISOR_TOKEN")
    if not access_token:
        raise StatisticsError("SUPERVISOR_TOKEN is missing; enable Home Assistant API access")

    identifier = statistic_id(mprn)
    metadata = {
        "has_sum": True,
        "mean_type": 0,
        "name": f"ESBN Hourly Grid Import ({identifier[-6:]})",
        "source": "esbn",
        "statistic_id": identifier,
        "unit_class": "energy",
        "unit_of_measurement": "kWh",
    }
    try:
        with connect(
            url,
            proxy=None,
            open_timeout=SOCKET_TIMEOUT_SECONDS,
            max_size=MAX_MESSAGE_BYTES,
        ) as socket:
            if _receive(socket).get("type") != "auth_required":
                raise StatisticsError("Home Assistant did not request authentication")
            socket.send(json.dumps({"type": "auth", "access_token": access_token}))
            if _receive(socket).get("type") != "auth_ok":
                raise StatisticsError("Home Assistant rejected the app token")

            updates = plan_updates(hourly, _recorded_sums(socket, identifier))
            for message_id, batch in enumerate(batched(updates, IMPORT_BATCH_SIZE), start=2):
                _command(
                    socket,
                    message_id,
                    "recorder/import_statistics",
                    metadata=metadata,
                    stats=[
                        {"start": hour.isoformat(), "state": total, "sum": total}
                        for hour, total in batch
                    ],
                )
    except (OSError, OverflowError, WebSocketException, ValueError) as exc:
        raise StatisticsError(f"Recorder communication failed ({type(exc).__name__})") from exc

    if updates:
        LOGGER.info("Submitted %s hourly import statistics for %s", len(updates), identifier)
    return len(updates)
