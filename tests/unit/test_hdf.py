from datetime import UTC
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


def test_parse_hdf_csv_rejects_missing_supported_kwh_columns() -> None:
    content = "Read Date and End Time,Voltage\n2026-05-12 00:30,230\n"

    with pytest.raises(HdfParseError, match="supported import or export kWh column"):
        parse_hdf_csv(content)


def test_parse_hdf_csv_wraps_invalid_numeric_cells() -> None:
    content = "Read Date and End Time,Import kWh\n2026-05-12 00:30,not-a-number\n"

    with pytest.raises(HdfParseError, match="Import kWh"):
        parse_hdf_csv(content)
