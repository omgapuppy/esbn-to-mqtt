from __future__ import annotations

import csv
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest
from esbn_to_mqtt.hdf import parse_hdf_csv
from esbn_to_mqtt.models import MeterReading, TariffConfig
from esbn_to_mqtt.state import AccumulatorState, backup_legacy_state

TARIFF = TariffConfig(enabled=True, day_rate=0.3, night_rate=0.1, peak_rate=0.5)
HEADER = "Read Date and End Time,Import kWh,Export kWh\n"
ROWS = [
    "2026-05-16 19:30,2.0,0.2",
    "2026-05-16 19:00,1.0,0.1",
    "2026-03-29 02:30,3.0,0.3",
    "2026-03-29 02:00,4.0,0.4",
    "2026-03-29 00:30,5.0,0.5",
    "2026-01-02 00:30,6.0,0.6",
    "2025-10-26 02:00,7.0,0.7",
    "2025-10-26 01:30,8.0,0.8",
    "2025-10-26 01:00,9.0,0.9",
    "2025-10-26 01:30,10.0,1.0",
    "2025-10-26 01:00,11.0,1.1",
    "2025-10-26 00:30,12.0,1.2",
]


def legacy_state(path: Path, content: str, *, values: bool = True) -> AccumulatorState:
    # Reproduce the released parser, including its stable sort of duplicate labels.
    readings = [
        MeterReading(
            timestamp=datetime.strptime(row["Read Date and End Time"], "%Y-%m-%d %H:%M")
            .replace(tzinfo=UTC) - timedelta(minutes=30),
            import_kwh=float(row["Import kWh"]),
            export_kwh=float(row["Export kWh"]),
        )
        for row in csv.DictReader(StringIO(content))
    ]
    state = AccumulatorState.empty().apply(readings).apply_tariff_costs(readings, TARIFF)
    state = replace(
        state,
        import_total_kwh=state.import_total_kwh + 100,
        export_total_kwh=state.export_total_kwh + 50,
        import_cost_total=state.import_cost_total + 25,
        last_hdf_latest_interval_start=state.last_interval_start,
        last_hdf_row_count=len(readings),
        hdf_export_stuck_polls=2,
    )
    state.save(path)
    payload = json.loads(path.read_text())
    payload.pop("hdf_timestamp_version", None)
    if not values:
        payload.pop("processed_interval_values")
        payload.pop("processed_cost_interval_values")
    path.write_text(json.dumps(payload))
    return AccumulatorState.load(path)


@pytest.mark.parametrize("ascending", [False, True])
def test_migration_replay_preserves_baseline_and_recovers_dst_values(
    tmp_path: Path, ascending: bool,
) -> None:
    content = HEADER + "\n".join(reversed(ROWS) if ascending else ROWS) + "\n"
    path = tmp_path / "state.json"
    legacy = legacy_state(path, content)
    readings = parse_hdf_csv(content)
    expected = AccumulatorState.empty().apply(readings).apply_tariff_costs(readings, TARIFF)

    migrated = legacy.migrate_hdf_timestamps()
    assert migrated.import_total_kwh == legacy.import_total_kwh
    assert migrated.export_total_kwh == legacy.export_total_kwh
    assert migrated.import_cost_total == legacy.import_cost_total
    assert migrated.last_interval_start == expected.last_interval_start
    assert migrated.last_hdf_latest_interval_start == expected.last_interval_start
    assert migrated.hdf_export_stuck_polls == 2

    updated = migrated.apply(readings).apply_tariff_costs(readings, TARIFF)
    assert updated.import_total_kwh == pytest.approx(expected.import_total_kwh + 100)
    assert updated.export_total_kwh == pytest.approx(expected.export_total_kwh + 50)
    assert updated.import_cost_total == pytest.approx(expected.import_cost_total + 25)
    assert updated.processed_interval_values == expected.processed_interval_values
    assert updated.processed_cost_interval_values == expected.processed_cost_interval_values

    updated.save(path)
    restarted = AccumulatorState.load(path).migrate_hdf_timestamps()
    assert restarted.apply(readings).apply_tariff_costs(readings, TARIFF) == updated


def test_migration_keeps_history_outside_the_current_export(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    content = HEADER + "2026-05-16 19:00,1.0,0.1\n2026-05-16 19:30,2.0,0.2\n"
    legacy = legacy_state(path, content)
    migrated = legacy.migrate_hdf_timestamps()

    assert migrated.processed_interval_values == {
        "2026-05-16T17:30:00+00:00:import": 1.0,
        "2026-05-16T17:30:00+00:00:export": 0.1,
        "2026-05-16T18:00:00+00:00:import": 2.0,
        "2026-05-16T18:00:00+00:00:export": 0.2,
    }
    partial = parse_hdf_csv(HEADER + "2026-05-16 19:30,2.0,0.2\n")
    assert migrated.apply(partial).import_total_kwh == legacy.import_total_kwh
    revised = parse_hdf_csv(HEADER + "2026-05-16 19:00,1.5,0.1\n")
    assert migrated.apply(revised).import_total_kwh == legacy.import_total_kwh + 0.5


def test_migration_does_not_replay_legacy_keys_without_values(tmp_path: Path) -> None:
    content = HEADER + "\n".join(ROWS) + "\n"
    legacy = legacy_state(tmp_path / "state.json", content, values=False)
    readings = parse_hdf_csv(content)

    migrated = legacy.migrate_hdf_timestamps().apply(readings).apply_tariff_costs(readings, TARIFF)

    assert migrated.import_total_kwh == legacy.import_total_kwh
    assert migrated.export_total_kwh == legacy.export_total_kwh
    assert migrated.import_cost_total == legacy.import_cost_total
    assert migrated.apply(readings).apply_tariff_costs(readings, TARIFF) == migrated


def test_current_state_is_not_migrated(tmp_path: Path) -> None:
    state = AccumulatorState.empty().apply(parse_hdf_csv(HEADER + ROWS[0] + "\n"))
    path = tmp_path / "state.json"
    state.save(path)

    assert AccumulatorState.load(path).migrate_hdf_timestamps() == state


@pytest.mark.parametrize("version", [0, 3, "2", True])
def test_unknown_state_version_is_rejected(tmp_path: Path, version: object) -> None:
    path = tmp_path / "state.json"
    AccumulatorState.empty().save(path)
    payload = json.loads(path.read_text())
    payload["hdf_timestamp_version"] = version
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="hdf_timestamp_version"):
        AccumulatorState.load(path)


def test_failed_atomic_save_keeps_original_and_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    path = tmp_path / "state.json"
    legacy = legacy_state(path, HEADER + ROWS[0] + "\n")
    original = path.read_bytes()
    backup_path = backup_legacy_state(path)

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("replace failed")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_replace)
        with pytest.raises(OSError, match="replace failed"):
            legacy.migrate_hdf_timestamps().save(path)

    assert path.read_bytes() == backup_path.read_bytes() == original
    assert set(tmp_path.iterdir()) == {path, backup_path}
    assert backup_legacy_state(path) == backup_path
    legacy.migrate_hdf_timestamps().save(path)
    assert AccumulatorState.load(path).hdf_timestamp_version == 2


def test_backup_is_not_overwritten_when_contents_differ(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    legacy_state(path, HEADER + ROWS[0] + "\n")
    backup_path = backup_legacy_state(path)
    backup_content = backup_path.read_bytes()
    path.write_text("different state")

    with pytest.raises(ValueError, match="backup differs"):
        backup_legacy_state(path)

    assert backup_path.read_bytes() == backup_content
