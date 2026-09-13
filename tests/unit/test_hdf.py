from datetime import UTC, datetime
from pathlib import Path

import pytest
from esbn_to_mqtt.hdf import HdfParseError, parse_hdf_csv
from esbn_to_mqtt.state import AccumulatorState


def test_parse_hdf_csv_reads_import_and_export_values() -> None:
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert len(rows) == 4
    assert rows[0].import_kwh == 0.120
    assert rows[2].export_kwh == 0.010
    assert rows[0].timestamp.tzinfo is not None
    assert rows[0].timestamp.utcoffset() == UTC.utcoffset(rows[0].timestamp)


def test_parse_hdf_csv_uses_interval_start_from_end_time() -> None:
    # The fixture's first row ends at 2026-05-12 00:30 Irish local, which is IST,
    # so the interval starts at 23:00 UTC on the previous day.
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert rows[0].timestamp.isoformat() == "2026-05-11T23:00:00+00:00"


def test_parse_hdf_csv_reads_end_times_as_irish_local_time() -> None:
    winter = parse_hdf_csv(
        "Read Date and End Time,Import kWh\n2026-01-15 12:00,0.100\n"
    )
    summer = parse_hdf_csv(
        "Read Date and End Time,Import kWh\n2026-07-15 12:00,0.100\n"
    )

    # GMT in January, so the label is already UTC.
    assert winter[0].timestamp == datetime(2026, 1, 15, 11, 30, tzinfo=UTC)
    # IST in July, so the label is an hour ahead of UTC.
    assert summer[0].timestamp == datetime(2026, 7, 15, 10, 30, tzinfo=UTC)


def test_parse_hdf_csv_reads_esbn_long_read_type_format() -> None:
    content = (
        "MPRN,Meter Serial Number,Read Value,Read Type,Read Date and End Time\n"
        "10000000000,123456789,0.1275,Active Import Interval (kWh),13-05-2026 02:00\n"
        "10000000000,123456789,0.0310,Active Export Interval (kWh),13-05-2026 02:00\n"
    )

    rows = parse_hdf_csv(content)

    assert len(rows) == 2
    assert rows[0].timestamp == datetime(2026, 5, 13, 0, 30, tzinfo=UTC)
    assert rows[0].import_kwh == 0.1275
    assert rows[0].export_kwh is None
    assert rows[0].quality == "Active Import Interval (kWh)"
    assert rows[1].timestamp == datetime(2026, 5, 13, 0, 30, tzinfo=UTC)
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


HEADER = "MPRN,Meter Serial Number,Read Value,Read Type,Read Date and End Time\n"


def _hdf(rows: list[tuple[str, float]]) -> str:
    # ESBN serves the export newest-first, so mirror that ordering here.
    body = "".join(
        f"10000000000,123456789,{value:.4f},Active Import Interval (kWh),{label}\n"
        for label, value in reversed(rows)
    )
    return HEADER + body


def test_parse_hdf_csv_splits_the_repeated_hour_on_the_autumn_transition() -> None:
    # Europe/Dublin 2026-10-25: 02:00 IST becomes 01:00 GMT, so ESBN emits 50 rows
    # for the day and the labels 01:00 and 01:30 each appear twice.
    rows = [
        ("25-10-2026 00:30", 0.10),
        ("25-10-2026 01:00", 0.20),
        ("25-10-2026 01:30", 0.30),
        ("25-10-2026 01:00", 0.40),
        ("25-10-2026 01:30", 0.50),
        ("25-10-2026 02:00", 0.60),
        ("25-10-2026 02:30", 0.70),
    ]

    parsed = parse_hdf_csv(_hdf(rows))

    assert len(parsed) == len(rows)
    assert len({reading.timestamp for reading in parsed}) == len(rows)
    assert sum(reading.import_kwh or 0.0 for reading in parsed) == pytest.approx(2.80)
    assert [reading.timestamp.isoformat() for reading in parsed] == [
        "2026-10-24T23:00:00+00:00",
        "2026-10-24T23:30:00+00:00",
        "2026-10-25T00:00:00+00:00",
        "2026-10-25T00:30:00+00:00",
        "2026-10-25T01:00:00+00:00",
        "2026-10-25T01:30:00+00:00",
        "2026-10-25T02:00:00+00:00",
    ]


def test_parse_hdf_csv_handles_the_missing_hour_on_the_spring_transition() -> None:
    # Europe/Dublin 2027-03-28: 01:00 GMT becomes 02:00 IST, so ESBN emits 46 rows
    # and the labels 01:00 and 01:30 never appear.
    rows = [
        ("28-03-2027 00:00", 0.05),
        ("28-03-2027 00:30", 0.10),
        ("28-03-2027 02:00", 0.30),
        ("28-03-2027 02:30", 0.40),
        ("28-03-2027 03:00", 0.50),
    ]

    parsed = parse_hdf_csv(_hdf(rows))

    assert [reading.timestamp.isoformat() for reading in parsed] == [
        "2027-03-27T23:30:00+00:00",
        "2027-03-28T00:00:00+00:00",
        "2027-03-28T00:30:00+00:00",
        "2027-03-28T01:00:00+00:00",
        "2027-03-28T01:30:00+00:00",
    ]


@pytest.mark.parametrize("ascending", [False, True])
def test_autumn_fold_is_counted_independently_for_import_and_export(ascending: bool) -> None:
    content = Path("tests/fixtures/esbn_autumn_channels_anonymized.csv").read_text()
    if ascending:
        header, *rows = content.splitlines()
        content = "\n".join([header, *reversed(rows)]) + "\n"

    readings = parse_hdf_csv(content)
    state = AccumulatorState.empty().apply(readings)

    assert len(readings) == 12
    assert state.import_total_kwh == 21.0
    assert state.export_total_kwh == 2.1
    assert len(state.processed_interval_values) == 12
    for hour_start, import_kwh in zip(
        ["23:00", "23:30", "00:00", "00:30", "01:00", "01:30"], range(1, 7), strict=True,
    ):
        day = "24" if hour_start.startswith("23") else "25"
        interval = f"2026-10-{day}T{hour_start}:00+00:00"
        assert state.processed_interval_values[f"{interval}:import"] == import_kwh
        assert state.processed_interval_values[f"{interval}:export"] == import_kwh / 10
    assert state.apply(readings) == state
