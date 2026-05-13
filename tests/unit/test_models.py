from datetime import UTC, datetime

from esbn_to_mqtt.models import MeterTotals


def test_meter_totals_defaults_to_immutable_processed_intervals() -> None:
    totals = MeterTotals(
        import_total_kwh=1.5,
        export_total_kwh=None,
        last_interval_start=None,
    )

    assert totals.processed_intervals == frozenset()
    assert isinstance(totals.processed_intervals, frozenset)


def test_meter_totals_converts_processed_intervals_to_immutable_set() -> None:
    processed_intervals = {"2026-05-13T00:00:00+00:00"}

    totals = MeterTotals(
        import_total_kwh=1.5,
        export_total_kwh=0.5,
        last_interval_start=datetime(2026, 5, 13, tzinfo=UTC),
        processed_intervals=processed_intervals,
    )

    processed_intervals.add("2026-05-13T00:30:00+00:00")

    assert totals.processed_intervals == frozenset({"2026-05-13T00:00:00+00:00"})
    assert isinstance(totals.processed_intervals, frozenset)
