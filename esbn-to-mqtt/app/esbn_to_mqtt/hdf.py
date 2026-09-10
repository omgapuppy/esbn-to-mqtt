from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from .models import MeterReading

# ESBN stamps the HDF in Irish wall-clock time, not UTC.
LOCAL_TZ = ZoneInfo("Europe/Dublin")
TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M")

DATE_COLUMNS = ("Read Date and End Time", "Read Date", "Date")
IMPORT_COLUMNS = ("Import kWh", "Consumption kWh", "kWh", "Active Import kWh")
EXPORT_COLUMNS = ("Export kWh", "Active Export kWh")
READ_VALUE_COLUMN = "Read Value"
READ_TYPE_COLUMN = "Read Type"

# (local interval end, import kWh, export kWh, quality)
_ParsedRow = tuple[datetime, float | None, float | None, str | None]


class HdfParseError(ValueError):
    pass


def _first_present(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _first_present_column_and_value(
    row: dict[str, str], names: Sequence[str]
) -> tuple[str, str] | tuple[None, None]:
    for name in names:
        value = row.get(name)
        if value is not None and value != "":
            return name, value
    return None, None


def _has_supported_column(fieldnames: Sequence[str], names: Sequence[str]) -> bool:
    return any(name in fieldnames for name in names)


def _has_long_read_type_columns(fieldnames: Sequence[str]) -> bool:
    return READ_VALUE_COLUMN in fieldnames and READ_TYPE_COLUMN in fieldnames


def _read_type_channels(row: dict[str, str]) -> tuple[str | None, str | None, str | None]:
    read_value = row.get(READ_VALUE_COLUMN)
    read_type = row.get(READ_TYPE_COLUMN)
    if read_value is None or read_value == "" or read_type is None or read_type == "":
        return None, None, read_type

    normalized_type = read_type.lower()
    if "kwh" not in normalized_type:
        return None, None, read_type
    if "import" in normalized_type:
        return read_value, None, read_type
    if "export" in normalized_type:
        return None, read_value, read_type
    return None, None, read_type


def _parse_float(value: str | None, column: str | None, line_num: int) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value.strip())
    except ValueError as exc:
        raise HdfParseError(
            f"invalid numeric value in HDF CSV row {line_num}, column {column!r}: {value!r}"
        ) from exc


def _parse_local_end_time(value: str) -> datetime:
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    raise HdfParseError(f"unsupported HDF timestamp format: {value!r}")


def _interval_start(local_end: datetime, fold: int) -> datetime:
    """Irish wall-clock interval END -> UTC interval START."""
    aware_end = local_end.replace(tzinfo=LOCAL_TZ, fold=fold)
    return aware_end.astimezone(UTC) - timedelta(minutes=30)


def _fold_flags(local_ends: Sequence[datetime]) -> list[int]:
    """Disambiguate the autumn repeated hour.

    On the October transition each wall-clock label between 01:00 and 01:59
    happens twice, once on IST and once on GMT, an hour apart in real time.
    ESBN serves the file newest-first, so the first of a repeated pair is the
    later instant. The ordering direction is read off the data.
    """
    if len(local_ends) < 2:
        return [0] * len(local_ends)

    descending = local_ends[0] > local_ends[-1]
    occurrences: dict[datetime, int] = {}
    for end in local_ends:
        occurrences[end] = occurrences.get(end, 0) + 1

    seen: dict[datetime, int] = {}
    flags: list[int] = []
    for end in local_ends:
        index = seen.get(end, 0)
        seen[end] = index + 1
        if occurrences[end] < 2:
            flags.append(0)
        elif descending:
            flags.append(min(occurrences[end] - 1 - index, 1))
        else:
            flags.append(min(index, 1))
    return flags


def parse_hdf_csv(content: str) -> list[MeterReading]:
    reader = csv.DictReader(StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise HdfParseError("HDF CSV has no header row")
    if not (
        _has_supported_column(reader.fieldnames, IMPORT_COLUMNS)
        or _has_supported_column(reader.fieldnames, EXPORT_COLUMNS)
        or _has_long_read_type_columns(reader.fieldnames)
    ):
        raise HdfParseError(
            "HDF CSV is missing a supported import or export kWh column"
        )

    parsed: list[_ParsedRow] = []
    for row in reader:
        date_value = _first_present(row, DATE_COLUMNS)
        if date_value is None:
            raise HdfParseError("HDF CSV is missing a supported date column")

        import_column, import_value = _first_present_column_and_value(row, IMPORT_COLUMNS)
        export_column, export_value = _first_present_column_and_value(row, EXPORT_COLUMNS)
        quality = row.get("Quality") or row.get("Read Quality")
        if import_value is None and export_value is None:
            long_import, long_export, read_type = _read_type_channels(row)
            if long_import is not None:
                import_column = READ_VALUE_COLUMN
                import_value = long_import
            if long_export is not None:
                export_column = READ_VALUE_COLUMN
                export_value = long_export
            quality = quality or read_type

        import_kwh = _parse_float(import_value, import_column, reader.line_num)
        export_kwh = _parse_float(export_value, export_column, reader.line_num)
        if import_kwh is None and export_kwh is None:
            continue

        parsed.append((_parse_local_end_time(date_value), import_kwh, export_kwh, quality))

    # Separate import/export rows repeat a label without repeating the interval.
    # Count folds per channel; keep row identity so duplicates remain revisions.
    readings: dict[tuple[int, datetime], MeterReading] = {}
    for channel, column in (("import_kwh", 1), ("export_kwh", 2)):
        channel_rows = [(index, row) for index, row in enumerate(parsed) if row[column] is not None]
        flags = _fold_flags([row[0] for _, row in channel_rows])
        for (index, parsed_row), fold in zip(channel_rows, flags, strict=True):
            timestamp = _interval_start(parsed_row[0], fold)
            key = (index, timestamp)
            reading = readings.get(key, MeterReading(timestamp=timestamp, quality=parsed_row[3]))
            readings[key] = (
                replace(reading, import_kwh=parsed_row[1]) if channel == "import_kwh"
                else replace(reading, export_kwh=parsed_row[2])
            )

    return sorted(readings.values(), key=lambda reading: reading.timestamp)
