from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Self

from .models import MeterReading, MeterTotals


@dataclass(frozen=True)
class AccumulatorState:
    import_total_kwh: float
    export_total_kwh: float | None
    last_interval_start: datetime | None
    processed_intervals: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "processed_intervals", frozenset(self.processed_intervals))

    @classmethod
    def empty(cls) -> Self:
        return cls(
            import_total_kwh=0.0,
            export_total_kwh=None,
            last_interval_start=None,
            processed_intervals=frozenset(),
        )

    @classmethod
    def load(cls, path: Path) -> Self:
        if not path.exists():
            return cls.empty()

        data = json.loads(path.read_text(encoding="utf-8"))
        last_interval = data.get("last_interval_start")
        return cls(
            import_total_kwh=float(data.get("import_total_kwh", 0.0)),
            export_total_kwh=(
                None if data.get("export_total_kwh") is None else float(data["export_total_kwh"])
            ),
            last_interval_start=(
                None if last_interval is None else datetime.fromisoformat(last_interval)
            ),
            processed_intervals=frozenset(data.get("processed_intervals", [])),
        )

    def apply(self, readings: list[MeterReading]) -> Self:
        import_total = self.import_total_kwh
        export_total = self.export_total_kwh
        processed = set(self.processed_intervals)
        last_interval = self.last_interval_start

        for reading in sorted(readings, key=lambda item: item.timestamp):
            last_interval = (
                reading.timestamp
                if last_interval is None
                else max(last_interval, reading.timestamp)
            )

            if reading.import_kwh is not None:
                interval_id = f"{reading.interval_id}:import"
                if interval_id not in processed:
                    import_total += reading.import_kwh
                    processed.add(interval_id)

            if reading.export_kwh is not None:
                interval_id = f"{reading.interval_id}:export"
                if interval_id not in processed:
                    export_total = (export_total or 0.0) + reading.export_kwh
                    processed.add(interval_id)

        return type(self)(
            import_total_kwh=round(import_total, 6),
            export_total_kwh=None if export_total is None else round(export_total, 6),
            last_interval_start=last_interval,
            processed_intervals=frozenset(processed),
        )

    def to_totals(self) -> MeterTotals:
        return MeterTotals(
            import_total_kwh=self.import_total_kwh,
            export_total_kwh=self.export_total_kwh,
            last_interval_start=self.last_interval_start,
            processed_intervals=self.processed_intervals,
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "import_total_kwh": self.import_total_kwh,
                    "export_total_kwh": self.export_total_kwh,
                    "last_interval_start": (
                        None
                        if self.last_interval_start is None
                        else self.last_interval_start.isoformat()
                    ),
                    "processed_intervals": sorted(self.processed_intervals),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
