from __future__ import annotations

import csv
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


def _parse_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value.strip())


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

    readings: list[MeterReading] = []
    for row in reader:
        date_value = _first_present(row, DATE_COLUMNS)
        if date_value is None:
            raise HdfParseError("HDF CSV is missing a supported date column")

        import_kwh = _parse_float(_first_present(row, IMPORT_COLUMNS))
        export_kwh = _parse_float(_first_present(row, EXPORT_COLUMNS))
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
