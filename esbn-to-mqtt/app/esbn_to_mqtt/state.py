from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Self

from .models import MeterReading, MeterTotals, TariffConfig
from .tariff import classify_tariff, tariff_rate


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
        if last_interval is not None and not isinstance(last_interval, str):
            raise ValueError("state last_interval_start must be a string or null")
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

    def apply(self, readings: list[MeterReading]) -> Self:
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
        )

    def apply_tariff_costs(self, readings: list[MeterReading], tariff: TariffConfig) -> Self:
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
        path.write_text(
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
            encoding="utf-8",
        )
