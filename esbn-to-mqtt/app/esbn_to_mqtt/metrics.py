from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .models import MeterMetrics, MeterReading

LOCAL_TZ = ZoneInfo("Europe/Dublin")


def _round_kwh(value: float) -> float:
    return round(value, 6)


def _latest_value(readings: list[MeterReading], field: str) -> float | None:
    for reading in sorted(readings, key=lambda item: item.timestamp, reverse=True):
        value = getattr(reading, field)
        if isinstance(value, float):
            return value
    return None


def _sum_for_local_day(readings: list[MeterReading], field: str, now: datetime) -> float | None:
    local_date = now.astimezone(LOCAL_TZ).date()
    values = [
        getattr(reading, field)
        for reading in readings
        if reading.timestamp.astimezone(LOCAL_TZ).date() == local_date
    ]
    numeric_values = [value for value in values if isinstance(value, float)]
    if not numeric_values:
        return None
    return _round_kwh(sum(numeric_values))


def _sum_for_local_month(readings: list[MeterReading], field: str, now: datetime) -> float | None:
    local_now = now.astimezone(LOCAL_TZ)
    values = [
        getattr(reading, field)
        for reading in readings
        if (
            reading.timestamp.astimezone(LOCAL_TZ).year == local_now.year
            and reading.timestamp.astimezone(LOCAL_TZ).month == local_now.month
        )
    ]
    numeric_values = [value for value in values if isinstance(value, float)]
    if not numeric_values:
        return None
    return _round_kwh(sum(numeric_values))


def build_meter_metrics(
    readings: list[MeterReading],
    *,
    processed_before: frozenset[str],
    processed_after: frozenset[str],
    auth_path: str,
    captcha_used: bool,
    now: datetime | None = None,
) -> MeterMetrics:
    timestamp = now or datetime.now(UTC)
    latest_interval = max((reading.timestamp for reading in readings), default=None)
    data_lag_hours = None
    if latest_interval is not None:
        data_lag_hours = round(
            (timestamp.astimezone(UTC) - latest_interval.astimezone(UTC)).total_seconds() / 3600,
            3,
        )

    today_import = _sum_for_local_day(readings, "import_kwh", timestamp) or 0.0
    month_import = _sum_for_local_month(readings, "import_kwh", timestamp) or 0.0

    return MeterMetrics(
        latest_import_interval_kwh=_latest_value(readings, "import_kwh"),
        latest_export_interval_kwh=_latest_value(readings, "export_kwh"),
        today_import_kwh=today_import,
        today_export_kwh=_sum_for_local_day(readings, "export_kwh", timestamp),
        current_month_import_kwh=month_import,
        current_month_export_kwh=_sum_for_local_month(readings, "export_kwh", timestamp),
        latest_esbn_interval_start=latest_interval,
        data_lag_hours=data_lag_hours,
        hdf_rows_parsed=len(readings),
        new_interval_values_processed=len(processed_after - processed_before),
        captcha_used=captcha_used,
        auth_path=auth_path,
    )
