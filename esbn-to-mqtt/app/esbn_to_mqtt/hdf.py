from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from io import StringIO

from .models import MeterReading

DATE_COLUMNS = ("Read Date and End Time", "Read Date", "Date")
IMPORT_COLUMNS = ("Import kWh", "Consumption kWh", "kWh", "Active Import kWh")
EXPORT_COLUMNS = ("Export kWh", "Active Export kWh")


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


def _parse_float(value: str | None, column: str | None, line_num: int) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        return float(value.strip())
    except ValueError as exc:
        raise HdfParseError(
            f"invalid numeric value in HDF CSV row {line_num}, column {column!r}: {value!r}"
        ) from exc


def _parse_end_time(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            end_time = datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
            return end_time - timedelta(minutes=30)
        except ValueError:
            continue
    raise HdfParseError(f"unsupported HDF timestamp format: {value!r}")


def parse_hdf_csv(content: str) -> list[MeterReading]:
    reader = csv.DictReader(StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise HdfParseError("HDF CSV has no header row")
    if not (
        _has_supported_column(reader.fieldnames, IMPORT_COLUMNS)
        or _has_supported_column(reader.fieldnames, EXPORT_COLUMNS)
    ):
        raise HdfParseError(
            "HDF CSV is missing a supported import or export kWh column"
        )

    readings: list[MeterReading] = []
    for row in reader:
        date_value = _first_present(row, DATE_COLUMNS)
        if date_value is None:
            raise HdfParseError("HDF CSV is missing a supported date column")

        import_column, import_value = _first_present_column_and_value(row, IMPORT_COLUMNS)
        export_column, export_value = _first_present_column_and_value(row, EXPORT_COLUMNS)
        import_kwh = _parse_float(import_value, import_column, reader.line_num)
        export_kwh = _parse_float(export_value, export_column, reader.line_num)
        if import_kwh is None and export_kwh is None:
            continue

        readings.append(
            MeterReading(
                timestamp=_parse_end_time(date_value),
                import_kwh=import_kwh,
                export_kwh=export_kwh,
                quality=row.get("Quality") or row.get("Read Quality"),
            )
        )

    return sorted(readings, key=lambda reading: reading.timestamp)
