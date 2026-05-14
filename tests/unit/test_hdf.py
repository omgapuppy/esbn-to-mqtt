from datetime import UTC, datetime
from pathlib import Path

import pytest
from esbn_to_mqtt.hdf import HdfParseError, parse_hdf_csv


def test_parse_hdf_csv_reads_import_and_export_values() -> None:
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert len(rows) == 4
    assert rows[0].import_kwh == 0.120
    assert rows[2].export_kwh == 0.010
    assert rows[0].timestamp.tzinfo is not None
    assert rows[0].timestamp.utcoffset() == UTC.utcoffset(rows[0].timestamp)


def test_parse_hdf_csv_uses_interval_start_from_end_time() -> None:
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert rows[0].timestamp.isoformat() == "2026-05-12T00:00:00+00:00"


def test_parse_hdf_csv_reads_esbn_long_read_type_format() -> None:
    content = (
        "MPRN,Meter Serial Number,Read Value,Read Type,Read Date and End Time\n"
        "10000000000,123456789,0.1275,Active Import Interval (kWh),13-05-2026 02:00\n"
        "10000000000,123456789,0.0310,Active Export Interval (kWh),13-05-2026 02:00\n"
    )

    rows = parse_hdf_csv(content)

    assert len(rows) == 2
    assert rows[0].timestamp == datetime(2026, 5, 13, 1, 30, tzinfo=UTC)
    assert rows[0].import_kwh == 0.1275
    assert rows[0].export_kwh is None
    assert rows[0].quality == "Active Import Interval (kWh)"
    assert rows[1].timestamp == datetime(2026, 5, 13, 1, 30, tzinfo=UTC)
    assert rows[1].import_kwh is None
    assert rows[1].export_kwh == 0.031
    assert rows[1].quality == "Active Export Interval (kWh)"


def test_parse_hdf_csv_rejects_missing_supported_kwh_columns() -> None:
    content = "Read Date and End Time,Voltage\n2026-05-12 00:30,230\n"

    with pytest.raises(HdfParseError, match="supported import or export kWh column"):
        parse_hdf_csv(content)


def test_parse_hdf_csv_wraps_invalid_numeric_cells() -> None:
    content = "Read Date and End Time,Import kWh\n2026-05-12 00:30,not-a-number\n"

    with pytest.raises(HdfParseError, match="Import kWh"):
        parse_hdf_csv(content)
