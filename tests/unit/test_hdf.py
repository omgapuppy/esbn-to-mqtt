from datetime import timezone
from pathlib import Path

from esbn_to_mqtt.hdf import parse_hdf_csv


def test_parse_hdf_csv_reads_import_and_export_values() -> None:
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert len(rows) == 4
    assert rows[0].import_kwh == 0.120
    assert rows[2].export_kwh == 0.010
    assert rows[0].timestamp.tzinfo is not None
    assert rows[0].timestamp.utcoffset() == timezone.utc.utcoffset(rows[0].timestamp)


def test_parse_hdf_csv_uses_interval_start_from_end_time() -> None:
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert rows[0].timestamp.isoformat() == "2026-05-12T00:00:00+00:00"
