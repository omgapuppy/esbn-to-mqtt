from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .models import MeterReading, TariffConfig

LOCAL_TZ = ZoneInfo("Europe/Dublin")
NIGHT_START = time(23, 0)
NIGHT_END = time(8, 0)
PEAK_START = time(17, 0)
PEAK_END = time(19, 0)


@dataclass(frozen=True)
class TariffSnapshot:
    name: str
    rate: float
    currency: str


def classify_tariff(timestamp: datetime) -> str:
    local_time = timestamp.astimezone(LOCAL_TZ).time()
    if local_time >= NIGHT_START or local_time < NIGHT_END:
        return "night"
    if PEAK_START <= local_time < PEAK_END:
        return "peak"
    return "day"


def tariff_rate(config: TariffConfig, tariff_name: str) -> float:
    if tariff_name == "night":
        return config.night_rate
    if tariff_name == "peak":
        return config.peak_rate
    return config.day_rate


def current_tariff_snapshot(
    config: TariffConfig,
    *,
    now: datetime,
) -> TariffSnapshot:
    name = classify_tariff(now)
    return TariffSnapshot(
        name=name,
        rate=tariff_rate(config, name),
        currency=config.currency,
    )


def calculate_import_cost(readings: list[MeterReading], config: TariffConfig) -> float:
    total = 0.0
    for reading in readings:
        if reading.import_kwh is None:
            continue
        total += reading.import_kwh * tariff_rate(config, classify_tariff(reading.timestamp))
    return round(total, 6)
