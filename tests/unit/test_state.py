from datetime import UTC, datetime

from esbn_to_mqtt.models import MeterReading
from esbn_to_mqtt.state import AccumulatorState


def reading(hour: int, import_kwh: float, export_kwh: float | None = None) -> MeterReading:
    return MeterReading(
        timestamp=datetime(2026, 5, 12, hour, 0, tzinfo=UTC),
        import_kwh=import_kwh,
        export_kwh=export_kwh,
    )


def test_accumulator_adds_only_new_intervals() -> None:
    state = AccumulatorState.empty()
    first = state.apply([reading(0, 1.0), reading(1, 2.0, 0.5)])
    second = first.apply([reading(1, 2.0, 0.5), reading(2, 3.0, 1.0)])

    assert second.import_total_kwh == 6.0
    assert second.export_total_kwh == 1.5
    assert second.processed_intervals == frozenset(
        {
            "2026-05-12T00:00:00+00:00:import",
            "2026-05-12T01:00:00+00:00:import",
            "2026-05-12T01:00:00+00:00:export",
            "2026-05-12T02:00:00+00:00:import",
            "2026-05-12T02:00:00+00:00:export",
        }
    )


def test_accumulator_round_trips_json(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = AccumulatorState.empty().apply([reading(0, 1.25)])
    state.save(path)

    loaded = AccumulatorState.load(path)
    assert loaded.import_total_kwh == 1.25
    assert loaded.processed_intervals == state.processed_intervals
