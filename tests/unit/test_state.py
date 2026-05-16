from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from esbn_to_mqtt.models import MeterReading, MeterTotals, TariffConfig
from esbn_to_mqtt.state import AccumulatorState


def test_empty_returns_expected_default_state() -> None:
    state = AccumulatorState.empty()

    assert state.import_total_kwh == 0.0
    assert state.import_cost_total == 0.0
    assert state.export_total_kwh is None
    assert state.last_interval_start is None
    assert state.processed_intervals == frozenset()
    assert state.processed_cost_intervals == frozenset()


def test_load_missing_path_returns_empty_state(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing" / "state.json"

    assert AccumulatorState.load(missing_path) == AccumulatorState.empty()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {
            "last_interval_start": "2024-01-02T03:30:00",
            "processed_intervals": ["2024-01-02T03:00:00:import"],
        },
        {
            "import_total_kwh": 12.5,
            "last_interval_start": "2024-01-02T03:30:00",
            "processed_intervals": ["2024-01-02T03:00:00:import"],
        },
        {"import_total_kwh": []},
        {"export_total_kwh": {}},
        {"last_interval_start": []},
        {"last_interval_start": "not-a-date"},
        {"processed_intervals": {}},
        {"processed_intervals": [1]},
    ],
)
def test_load_rejects_malformed_state_json_shapes(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        AccumulatorState.load(path)


def test_load_parses_export_last_interval_and_processed_intervals(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "import_total_kwh": 12.5,
                "export_total_kwh": 7.25,
                "last_interval_start": "2024-01-02T03:30:00",
                "processed_intervals": [
                    "2024-01-02T02:30:00:export",
                    "2024-01-02T03:00:00:import",
                ],
            }
        ),
        encoding="utf-8",
    )

    state = AccumulatorState.load(path)

    assert state.import_total_kwh == 12.5
    assert state.export_total_kwh == 7.25
    assert state.last_interval_start == datetime.fromisoformat("2024-01-02T03:30:00")
    assert state.processed_intervals == frozenset(
        {
            "2024-01-02T02:30:00:export",
            "2024-01-02T03:00:00:import",
        }
    )


def test_apply_sorts_by_timestamp_updates_latest_interval_and_rounds_totals() -> None:
    initial_state = AccumulatorState(
        import_total_kwh=1.0,
        export_total_kwh=2.0,
        last_interval_start=datetime.fromisoformat("2024-01-02T00:00:00"),
        processed_intervals=frozenset(),
    )
    readings = [
        MeterReading(
            timestamp=datetime.fromisoformat("2024-01-02T00:15:00"),
            import_kwh=0.2222227,
        ),
        MeterReading(
            timestamp=datetime.fromisoformat("2024-01-02T00:45:00"),
            export_kwh=0.4444447,
        ),
        MeterReading(
            timestamp=datetime.fromisoformat("2024-01-02T00:30:00"),
            import_kwh=0.1111114,
            export_kwh=0.3333334,
        ),
    ]

    state = initial_state.apply(readings)

    assert state.import_total_kwh == 1.333334
    assert state.export_total_kwh == 2.777778
    assert state.last_interval_start == datetime.fromisoformat("2024-01-02T00:45:00")
    assert state.processed_intervals == frozenset(
        {
            "2024-01-02T00:15:00:import",
            "2024-01-02T00:30:00:import",
            "2024-01-02T00:30:00:export",
            "2024-01-02T00:45:00:export",
        }
    )


def test_apply_only_adds_unseen_import_export_interval_ids() -> None:
    initial_state = AccumulatorState.empty().apply(
        [
            MeterReading(
                timestamp=datetime.fromisoformat("2024-01-02T00:15:00"),
                import_kwh=1.2,
                export_kwh=0.4,
            ),
            MeterReading(
                timestamp=datetime.fromisoformat("2024-01-02T00:30:00"),
                import_kwh=0.8,
            ),
        ]
    )
    reapplied_readings = [
        MeterReading(
            timestamp=datetime.fromisoformat("2024-01-02T00:15:00"),
            import_kwh=1.2,
            export_kwh=0.4,
        ),
        MeterReading(
            timestamp=datetime.fromisoformat("2024-01-02T00:30:00"),
            import_kwh=0.8,
        ),
        MeterReading(
            timestamp=datetime.fromisoformat("2024-01-02T00:45:00"),
            import_kwh=0.5,
            export_kwh=0.25,
        ),
        MeterReading(
            timestamp=datetime.fromisoformat("2024-01-02T00:45:00"),
            import_kwh=0.5,
            export_kwh=0.25,
        ),
    ]

    state = initial_state.apply(reapplied_readings)

    assert state.import_total_kwh == 2.5
    assert state.export_total_kwh == 0.65
    assert state.processed_intervals == frozenset(
        {
            "2024-01-02T00:15:00:import",
            "2024-01-02T00:15:00:export",
            "2024-01-02T00:30:00:import",
            "2024-01-02T00:45:00:import",
            "2024-01-02T00:45:00:export",
        }
    )


def test_apply_tariff_costs_only_charges_unseen_import_intervals() -> None:
    tariff = TariffConfig(
        enabled=True,
        day_rate=0.30,
        night_rate=0.15,
        peak_rate=0.45,
        currency="EUR",
    )
    initial_state = AccumulatorState.empty().apply_tariff_costs(
        [
            MeterReading(
                timestamp=datetime.fromisoformat("2026-05-16T06:30:00+00:00"),
                import_kwh=1.0,
            )
        ],
        tariff,
    )

    state = initial_state.apply_tariff_costs(
        [
            MeterReading(
                timestamp=datetime.fromisoformat("2026-05-16T06:30:00+00:00"),
                import_kwh=1.0,
            ),
            MeterReading(
                timestamp=datetime.fromisoformat("2026-05-16T16:30:00+00:00"),
                import_kwh=2.0,
            ),
            MeterReading(
                timestamp=datetime.fromisoformat("2026-05-16T18:30:00+00:00"),
                export_kwh=3.0,
            ),
        ],
        tariff,
    )

    assert state.import_cost_total == 1.05
    assert state.processed_cost_intervals == frozenset(
        {
            "2026-05-16T06:30:00+00:00:import_cost",
            "2026-05-16T16:30:00+00:00:import_cost",
        }
    )


def test_to_totals_returns_matching_meter_totals_with_immutable_processed_intervals() -> None:
    state = AccumulatorState(
        import_total_kwh=9.5,
        import_cost_total=4.25,
        export_total_kwh=1.25,
        last_interval_start=datetime.fromisoformat("2024-01-02T00:30:00"),
        processed_intervals={"2024-01-02T00:30:00:import"},
        processed_cost_intervals={"2024-01-02T00:30:00:import_cost"},
    )

    totals = state.to_totals()

    assert totals == MeterTotals(
        import_total_kwh=9.5,
        import_cost_total=4.25,
        export_total_kwh=1.25,
        last_interval_start=datetime.fromisoformat("2024-01-02T00:30:00"),
        processed_intervals=frozenset({"2024-01-02T00:30:00:import"}),
        processed_cost_intervals=frozenset({"2024-01-02T00:30:00:import_cost"}),
    )
    assert isinstance(totals.processed_intervals, frozenset)
    with pytest.raises(AttributeError):
        totals.processed_intervals.add("2024-01-02T00:45:00:export")


def test_save_creates_parent_directories_and_writes_pretty_sorted_json(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    state = AccumulatorState(
        import_total_kwh=8.75,
        import_cost_total=3.33,
        export_total_kwh=1.5,
        last_interval_start=datetime.fromisoformat("2024-01-02T00:30:00"),
        processed_intervals={
            "2024-01-02T00:45:00:export",
            "2024-01-02T00:30:00:import",
        },
        processed_cost_intervals={"2024-01-02T00:30:00:import_cost"},
    )

    state.save(path)

    assert path.exists()
    assert path.read_text(encoding="utf-8") == (
        '{\n'
        '  "export_total_kwh": 1.5,\n'
        '  "import_cost_total": 3.33,\n'
        '  "import_total_kwh": 8.75,\n'
        '  "last_interval_start": "2024-01-02T00:30:00",\n'
        '  "processed_cost_intervals": [\n'
        '    "2024-01-02T00:30:00:import_cost"\n'
        "  ],\n"
        '  "processed_intervals": [\n'
        '    "2024-01-02T00:30:00:import",\n'
        '    "2024-01-02T00:45:00:export"\n'
        "  ]\n"
        "}\n"
    )


def test_save_and_load_round_trip_preserves_accumulator_state(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    state = AccumulatorState(
        import_total_kwh=8.75,
        import_cost_total=3.33,
        export_total_kwh=1.5,
        last_interval_start=datetime.fromisoformat("2024-01-02T00:30:00"),
        processed_intervals={
            "2024-01-02T00:30:00:import",
            "2024-01-02T00:45:00:export",
        },
        processed_cost_intervals={"2024-01-02T00:30:00:import_cost"},
    )

    state.save(path)

    loaded_state = AccumulatorState.load(path)

    assert loaded_state.import_total_kwh == state.import_total_kwh
    assert loaded_state.import_cost_total == state.import_cost_total
    assert loaded_state.export_total_kwh == state.export_total_kwh
    assert loaded_state.last_interval_start == state.last_interval_start
    assert loaded_state.processed_intervals == state.processed_intervals
    assert loaded_state.processed_cost_intervals == state.processed_cost_intervals
