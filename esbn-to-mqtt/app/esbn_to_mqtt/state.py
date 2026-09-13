from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import MappingProxyType
from typing import Self

from .hdf import LOCAL_TZ
from .models import MeterReading, MeterTotals, TariffConfig
from .tariff import classify_tariff, tariff_rate

HDF_EXPORT_STUCK_WARNING_POLLS = 2
HDF_TIMESTAMP_VERSION = 2


def _migrate_timestamp(timestamp: datetime, *, fold: int = 0) -> datetime:
    # Undo the old interval-end subtraction before interpreting the wall clock.
    local_end = (timestamp + timedelta(minutes=30)).replace(tzinfo=LOCAL_TZ, fold=fold)
    return local_end.astimezone(UTC) - timedelta(minutes=30)


def _migrate_interval_keys(
    processed: frozenset[str], values: Mapping[str, float],
) -> tuple[frozenset[str], dict[str, float]]:
    migrated: set[str] = set()
    migrated_values: dict[str, float] = {}
    for interval_id in processed | values.keys():
        timestamp_text, channel = interval_id.rsplit(":", 1)
        timestamp = datetime.fromisoformat(timestamp_text)
        new_id = f"{_migrate_timestamp(timestamp).isoformat()}:{channel}"
        if new_id in migrated:
            raise ValueError("legacy interval keys collide after timezone migration")
        migrated.add(new_id)
        if interval_id in values:
            # A collapsed autumn value is a baseline for the pair. Replaying both
            # corrected readings replaces it with their sum via normal revisions.
            migrated_values[new_id] = values[interval_id]
        else:
            # Keys-only states cannot tell us the old contribution. Prime both
            # autumn folds without adding either again; preserve the saved total.
            migrated.add(f"{_migrate_timestamp(timestamp, fold=1).isoformat()}:{channel}")
    return frozenset(migrated), migrated_values


def _atomic_write(path: Path, content: str) -> None:
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary_path = Path(file.name)
        try:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def backup_legacy_state(path: Path) -> Path:
    backup_path = path.with_name(f"{path.name}.before-local-time")
    content = path.read_text(encoding="utf-8")
    if backup_path.exists():
        if backup_path.read_text(encoding="utf-8") != content:
            raise ValueError("existing timezone migration backup differs from legacy state")
    else:
        _atomic_write(backup_path, content)
    return backup_path


@dataclass(frozen=True)
class AccumulatorState:
    import_total_kwh: float
    export_total_kwh: float | None
    last_interval_start: datetime | None
    processed_intervals: frozenset[str] = field(default_factory=frozenset)
    processed_interval_values: Mapping[str, float] = field(default_factory=dict)
    import_cost_total: float = 0.0
    processed_cost_intervals: frozenset[str] = field(default_factory=frozenset)
    processed_cost_interval_values: Mapping[str, float] = field(default_factory=dict)
    last_hdf_row_count: int | None = None
    last_hdf_latest_interval_start: datetime | None = None
    hdf_export_stuck_polls: int = 0
    hdf_timestamp_version: int = HDF_TIMESTAMP_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "processed_intervals", frozenset(self.processed_intervals))
        object.__setattr__(
            self,
            "processed_interval_values",
            MappingProxyType(
                {key: float(value) for key, value in self.processed_interval_values.items()}
            ),
        )
        object.__setattr__(
            self,
            "processed_cost_intervals",
            frozenset(self.processed_cost_intervals),
        )
        object.__setattr__(
            self,
            "processed_cost_interval_values",
            MappingProxyType(
                {
                    key: float(value)
                    for key, value in self.processed_cost_interval_values.items()
                }
            ),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls(
            import_total_kwh=0.0,
            export_total_kwh=None,
            last_interval_start=None,
            processed_intervals=frozenset(),
            processed_interval_values={},
            import_cost_total=0.0,
            processed_cost_intervals=frozenset(),
            processed_cost_interval_values={},
            last_hdf_row_count=None,
            last_hdf_latest_interval_start=None,
            hdf_export_stuck_polls=0,
        )

    @classmethod
    def load(cls, path: Path) -> Self:
        if not path.exists():
            return cls.empty()

        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("state file must contain a JSON object")
        if "import_total_kwh" not in data:
            raise ValueError("state import_total_kwh is required")
        if "export_total_kwh" not in data:
            raise ValueError("state export_total_kwh is required")
        last_interval = data.get("last_interval_start")
        processed_intervals = data.get("processed_intervals", [])
        processed_interval_values = data.get("processed_interval_values", {})
        processed_cost_intervals = data.get("processed_cost_intervals", [])
        processed_cost_interval_values = data.get("processed_cost_interval_values", {})
        last_hdf_row_count = data.get("last_hdf_row_count")
        last_hdf_latest_interval = data.get("last_hdf_latest_interval_start")
        hdf_export_stuck_polls = data.get("hdf_export_stuck_polls", 0)
        hdf_timestamp_version = data.get("hdf_timestamp_version", 1)
        if type(hdf_timestamp_version) is not int or hdf_timestamp_version not in (
            1, HDF_TIMESTAMP_VERSION,
        ):
            raise ValueError("state hdf_timestamp_version is unsupported")
        if last_interval is not None and not isinstance(last_interval, str):
            raise ValueError("state last_interval_start must be a string or null")
        if last_hdf_latest_interval is not None and not isinstance(
            last_hdf_latest_interval, str
        ):
            raise ValueError("state last_hdf_latest_interval_start must be a string or null")
        if last_hdf_row_count is not None and not isinstance(last_hdf_row_count, int):
            raise ValueError("state last_hdf_row_count must be an integer or null")
        if not isinstance(hdf_export_stuck_polls, int):
            raise ValueError("state hdf_export_stuck_polls must be an integer")
        if not isinstance(processed_intervals, list) or not all(
            isinstance(interval, str) for interval in processed_intervals
        ):
            raise ValueError("state processed_intervals must be a list of strings")
        if not isinstance(processed_interval_values, dict) or not all(
            isinstance(interval, str) and isinstance(value, int | float)
            for interval, value in processed_interval_values.items()
        ):
            raise ValueError("state processed_interval_values must map strings to numbers")
        if not isinstance(processed_cost_intervals, list) or not all(
            isinstance(interval, str) for interval in processed_cost_intervals
        ):
            raise ValueError("state processed_cost_intervals must be a list of strings")
        if not isinstance(processed_cost_interval_values, dict) or not all(
            isinstance(interval, str) and isinstance(value, int | float)
            for interval, value in processed_cost_interval_values.items()
        ):
            raise ValueError("state processed_cost_interval_values must map strings to numbers")

        try:
            return cls(
                import_total_kwh=float(data["import_total_kwh"]),
                import_cost_total=float(data.get("import_cost_total", 0.0)),
                export_total_kwh=(
                    None
                    if data.get("export_total_kwh") is None
                    else float(data["export_total_kwh"])
                ),
                last_interval_start=(
                    None if last_interval is None else datetime.fromisoformat(last_interval)
                ),
                last_hdf_latest_interval_start=(
                    None
                    if last_hdf_latest_interval is None
                    else datetime.fromisoformat(last_hdf_latest_interval)
                ),
                last_hdf_row_count=last_hdf_row_count,
                hdf_export_stuck_polls=hdf_export_stuck_polls,
                hdf_timestamp_version=hdf_timestamp_version,
                processed_intervals=frozenset(processed_intervals),
                processed_interval_values={
                    interval: float(value)
                    for interval, value in processed_interval_values.items()
                },
                processed_cost_intervals=frozenset(processed_cost_intervals),
                processed_cost_interval_values={
                    interval: float(value)
                    for interval, value in processed_cost_interval_values.items()
                },
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("state file contained invalid accumulator values") from exc

    @property
    def hdf_export_stuck(self) -> bool:
        return self.hdf_export_stuck_polls >= HDF_EXPORT_STUCK_WARNING_POLLS

    def migrate_hdf_timestamps(self) -> Self:
        if self.hdf_timestamp_version == HDF_TIMESTAMP_VERSION:
            return self
        if self.hdf_timestamp_version != 1:
            raise ValueError("state hdf_timestamp_version is unsupported")
        processed, values = _migrate_interval_keys(
            self.processed_intervals, self.processed_interval_values,
        )
        cost_processed, cost_values = _migrate_interval_keys(
            self.processed_cost_intervals, self.processed_cost_interval_values,
        )
        return replace(
            self,
            processed_intervals=processed,
            processed_interval_values=values,
            processed_cost_intervals=cost_processed,
            processed_cost_interval_values=cost_values,
            last_interval_start=(
                None if self.last_interval_start is None
                else _migrate_timestamp(self.last_interval_start)
            ),
            last_hdf_latest_interval_start=(
                None if self.last_hdf_latest_interval_start is None
                else _migrate_timestamp(self.last_hdf_latest_interval_start)
            ),
            hdf_timestamp_version=HDF_TIMESTAMP_VERSION,
        )

    def apply(self, readings: list[MeterReading]) -> Self:
        if self.hdf_timestamp_version != HDF_TIMESTAMP_VERSION:
            raise ValueError("legacy HDF timestamps must be migrated before applying readings")
        import_total = self.import_total_kwh
        export_total = self.export_total_kwh
        processed = set(self.processed_intervals)
        processed_values = dict(self.processed_interval_values)
        last_interval = self.last_interval_start

        for reading in sorted(readings, key=lambda item: item.timestamp):
            last_interval = (
                reading.timestamp
                if last_interval is None
                else max(last_interval, reading.timestamp)
            )

            if reading.import_kwh is not None:
                interval_id = f"{reading.interval_id}:import"
                if interval_id in processed_values:
                    import_total += reading.import_kwh - processed_values[interval_id]
                    processed_values[interval_id] = reading.import_kwh
                elif interval_id in processed:
                    processed_values[interval_id] = reading.import_kwh
                else:
                    import_total += reading.import_kwh
                    processed.add(interval_id)
                    processed_values[interval_id] = reading.import_kwh

            if reading.export_kwh is not None:
                interval_id = f"{reading.interval_id}:export"
                if interval_id in processed_values:
                    export_total = (export_total or 0.0) + (
                        reading.export_kwh - processed_values[interval_id]
                    )
                    processed_values[interval_id] = reading.export_kwh
                elif interval_id in processed:
                    processed_values[interval_id] = reading.export_kwh
                else:
                    export_total = (export_total or 0.0) + reading.export_kwh
                    processed.add(interval_id)
                    processed_values[interval_id] = reading.export_kwh

        return type(self)(
            import_total_kwh=round(import_total, 6),
            export_total_kwh=None if export_total is None else round(export_total, 6),
            last_interval_start=last_interval,
            processed_intervals=frozenset(processed),
            processed_interval_values=processed_values,
            import_cost_total=self.import_cost_total,
            processed_cost_intervals=self.processed_cost_intervals,
            processed_cost_interval_values=self.processed_cost_interval_values,
            last_hdf_row_count=self.last_hdf_row_count,
            last_hdf_latest_interval_start=self.last_hdf_latest_interval_start,
            hdf_export_stuck_polls=self.hdf_export_stuck_polls,
        )

    def apply_tariff_costs(self, readings: list[MeterReading], tariff: TariffConfig) -> Self:
        if self.hdf_timestamp_version != HDF_TIMESTAMP_VERSION:
            raise ValueError("legacy HDF timestamps must be migrated before applying costs")
        if not tariff.enabled:
            return self

        cost_total = self.import_cost_total
        processed = set(self.processed_cost_intervals)
        processed_values = dict(self.processed_cost_interval_values)
        for reading in sorted(readings, key=lambda item: item.timestamp):
            if reading.import_kwh is None:
                continue
            interval_id = f"{reading.interval_id}:import_cost"
            interval_cost = reading.import_kwh * tariff_rate(
                tariff,
                classify_tariff(reading.timestamp),
            )
            if interval_id in processed_values:
                cost_total += interval_cost - processed_values[interval_id]
                processed_values[interval_id] = interval_cost
                continue
            if interval_id in processed:
                processed_values[interval_id] = interval_cost
                continue
            cost_total += interval_cost
            processed.add(interval_id)
            processed_values[interval_id] = interval_cost

        return type(self)(
            import_total_kwh=self.import_total_kwh,
            export_total_kwh=self.export_total_kwh,
            last_interval_start=self.last_interval_start,
            processed_intervals=self.processed_intervals,
            processed_interval_values=self.processed_interval_values,
            import_cost_total=round(cost_total, 6),
            processed_cost_intervals=frozenset(processed),
            processed_cost_interval_values=processed_values,
            last_hdf_row_count=self.last_hdf_row_count,
            last_hdf_latest_interval_start=self.last_hdf_latest_interval_start,
            hdf_export_stuck_polls=self.hdf_export_stuck_polls,
        )

    def record_hdf_observation(
        self,
        *,
        row_count: int,
        latest_interval_start: datetime | None,
    ) -> Self:
        stuck_poll = (
            latest_interval_start is not None
            and self.last_hdf_latest_interval_start == latest_interval_start
            and self.last_hdf_row_count is not None
            and row_count < self.last_hdf_row_count
        )
        stuck_polls = self.hdf_export_stuck_polls + 1 if stuck_poll else 0
        return type(self)(
            import_total_kwh=self.import_total_kwh,
            export_total_kwh=self.export_total_kwh,
            last_interval_start=self.last_interval_start,
            processed_intervals=self.processed_intervals,
            processed_interval_values=self.processed_interval_values,
            import_cost_total=self.import_cost_total,
            processed_cost_intervals=self.processed_cost_intervals,
            processed_cost_interval_values=self.processed_cost_interval_values,
            last_hdf_row_count=row_count,
            last_hdf_latest_interval_start=latest_interval_start,
            hdf_export_stuck_polls=stuck_polls,
            hdf_timestamp_version=self.hdf_timestamp_version,
        )

    def to_totals(self) -> MeterTotals:
        return MeterTotals(
            import_total_kwh=self.import_total_kwh,
            export_total_kwh=self.export_total_kwh,
            last_interval_start=self.last_interval_start,
            processed_intervals=self.processed_intervals,
            import_cost_total=self.import_cost_total,
            processed_cost_intervals=self.processed_cost_intervals,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(
            path,
            json.dumps(
                {
                    "import_total_kwh": self.import_total_kwh,
                    "import_cost_total": self.import_cost_total,
                    "export_total_kwh": self.export_total_kwh,
                    "last_interval_start": (
                        None
                        if self.last_interval_start is None
                        else self.last_interval_start.isoformat()
                    ),
                    "last_hdf_latest_interval_start": (
                        None
                        if self.last_hdf_latest_interval_start is None
                        else self.last_hdf_latest_interval_start.isoformat()
                    ),
                    "last_hdf_row_count": self.last_hdf_row_count,
                    "hdf_export_stuck_polls": self.hdf_export_stuck_polls,
                    "hdf_timestamp_version": self.hdf_timestamp_version,
                    "processed_cost_interval_values": dict(
                        self.processed_cost_interval_values
                    ),
                    "processed_intervals": sorted(self.processed_intervals),
                    "processed_interval_values": dict(self.processed_interval_values),
                    "processed_cost_intervals": sorted(self.processed_cost_intervals),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
