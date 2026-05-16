from __future__ import annotations

from datetime import UTC, datetime

from esbn_to_mqtt.metrics import build_meter_metrics
from esbn_to_mqtt.models import MeterReading


def test_build_meter_metrics_summarizes_recent_periods_and_diagnostics() -> None:
    readings = [
        MeterReading(
            timestamp=datetime(2026, 5, 15, 22, 30, tzinfo=UTC),
            import_kwh=0.5,
            export_kwh=0.1,
        ),
        MeterReading(
            timestamp=datetime(2026, 5, 16, 7, 0, tzinfo=UTC),
            import_kwh=0.25,
            export_kwh=None,
        ),
        MeterReading(
            timestamp=datetime(2026, 5, 16, 18, 30, tzinfo=UTC),
            import_kwh=0.75,
            export_kwh=0.2,
        ),
    ]

    metrics = build_meter_metrics(
        readings,
        processed_before=frozenset({"2026-05-16T07:00:00+00:00:import"}),
        processed_after=frozenset(
            {
                "2026-05-16T07:00:00+00:00:import",
                "2026-05-16T18:30:00+00:00:import",
                "2026-05-16T18:30:00+00:00:export",
            }
        ),
        auth_path="login+captcha",
        captcha_used=True,
        now=datetime(2026, 5, 16, 20, 0, tzinfo=UTC),
    )

    assert metrics.latest_import_interval_kwh == 0.75
    assert metrics.latest_export_interval_kwh == 0.2
    assert metrics.today_import_kwh == 1.0
    assert metrics.today_export_kwh == 0.2
    assert metrics.current_month_import_kwh == 1.5
    assert metrics.current_month_export_kwh == 0.3
    assert metrics.latest_esbn_interval_start == datetime(2026, 5, 16, 18, 30, tzinfo=UTC)
    assert metrics.data_lag_hours == 1.5
    assert metrics.hdf_rows_parsed == 3
    assert metrics.new_interval_values_processed == 2
    assert metrics.auth_path == "login+captcha"
    assert metrics.captcha_used is True


def test_build_meter_metrics_omits_export_values_when_no_export_readings_exist() -> None:
    metrics = build_meter_metrics(
        [MeterReading(timestamp=datetime(2026, 5, 16, 18, 30, tzinfo=UTC), import_kwh=0.75)],
        processed_before=frozenset(),
        processed_after=frozenset({"2026-05-16T18:30:00+00:00:import"}),
        auth_path="cookie",
        captcha_used=False,
        now=datetime(2026, 5, 16, 20, 0, tzinfo=UTC),
    )

    assert metrics.latest_export_interval_kwh is None
    assert metrics.today_export_kwh is None
    assert metrics.current_month_export_kwh is None
    assert metrics.auth_path == "cookie"
    assert metrics.captcha_used is False
