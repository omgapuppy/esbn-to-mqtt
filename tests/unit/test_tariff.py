from __future__ import annotations

from datetime import UTC, datetime

from esbn_to_mqtt.models import MeterReading, TariffConfig
from esbn_to_mqtt.tariff import (
    calculate_import_cost,
    classify_tariff,
    current_tariff_snapshot,
)


def tariff_config() -> TariffConfig:
    return TariffConfig(
        enabled=True,
        day_rate=0.30,
        night_rate=0.15,
        peak_rate=0.45,
        currency="EUR",
    )


def test_classify_tariff_uses_yuno_smart_periods_in_europe_dublin_time() -> None:
    assert classify_tariff(datetime(2026, 5, 16, 6, 30, tzinfo=UTC)) == "night"
    assert classify_tariff(datetime(2026, 5, 16, 7, 0, tzinfo=UTC)) == "day"
    assert classify_tariff(datetime(2026, 5, 16, 16, 0, tzinfo=UTC)) == "peak"
    assert classify_tariff(datetime(2026, 5, 16, 18, 0, tzinfo=UTC)) == "day"
    assert classify_tariff(datetime(2026, 5, 16, 22, 0, tzinfo=UTC)) == "night"


def test_calculate_import_cost_uses_tariff_rate_for_interval_start() -> None:
    readings = [
        MeterReading(timestamp=datetime(2026, 5, 16, 6, 30, tzinfo=UTC), import_kwh=1.0),
        MeterReading(timestamp=datetime(2026, 5, 16, 16, 30, tzinfo=UTC), import_kwh=2.0),
        MeterReading(timestamp=datetime(2026, 5, 16, 18, 30, tzinfo=UTC), import_kwh=3.0),
    ]

    assert calculate_import_cost(readings, tariff_config()) == 1.95


def test_current_tariff_snapshot_returns_name_and_rate() -> None:
    snapshot = current_tariff_snapshot(
        tariff_config(),
        now=datetime(2026, 5, 16, 16, 15, tzinfo=UTC),
    )

    assert snapshot.name == "peak"
    assert snapshot.rate == 0.45
    assert snapshot.currency == "EUR"
