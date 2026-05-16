from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class EsbnCredentials:
    username: str
    password: str
    mprn: str


@dataclass(frozen=True)
class MqttConfig:
    host: str
    port: int
    username: str
    password: str
    discovery_prefix: str = "homeassistant"
    topic_prefix: str = "esbn_to_mqtt"


@dataclass(frozen=True)
class CaptchaConfig:
    solver: str = "disabled"
    two_captcha_api_key: str | None = None
    two_captcha_timeout_seconds: int = 120


@dataclass(frozen=True)
class TariffConfig:
    enabled: bool = False
    day_rate: float = 0.0
    night_rate: float = 0.0
    peak_rate: float = 0.0
    currency: str = "EUR"


@dataclass(frozen=True)
class MeterReading:
    timestamp: datetime
    import_kwh: float | None = None
    export_kwh: float | None = None
    quality: str | None = None

    @property
    def interval_id(self) -> str:
        return self.timestamp.isoformat()


@dataclass(frozen=True)
class AppConfig:
    esbn: EsbnCredentials
    mqtt: MqttConfig
    poll_interval_hours: int
    log_level: str
    captcha: CaptchaConfig = CaptchaConfig()
    tariff: TariffConfig = TariffConfig()

    @property
    def mprn(self) -> str:
        return self.esbn.mprn

    @property
    def poll_interval_seconds(self) -> int:
        return self.poll_interval_hours * 60 * 60


@dataclass(frozen=True)
class MeterTotals:
    import_total_kwh: float
    export_total_kwh: float | None
    last_interval_start: datetime | None
    processed_intervals: frozenset[str] = field(default_factory=frozenset)
    import_cost_total: float = 0.0
    processed_cost_intervals: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "processed_intervals", frozenset(self.processed_intervals))
        object.__setattr__(
            self,
            "processed_cost_intervals",
            frozenset(self.processed_cost_intervals),
        )


@dataclass(frozen=True)
class MeterMetrics:
    latest_import_interval_kwh: float | None
    latest_export_interval_kwh: float | None
    today_import_kwh: float
    today_export_kwh: float | None
    current_month_import_kwh: float
    current_month_export_kwh: float | None
    latest_esbn_interval_start: datetime | None
    data_lag_hours: float | None
    hdf_rows_parsed: int
    new_interval_values_processed: int
    captcha_used: bool
    auth_path: str
    today_import_cost: float | None = None
    current_month_import_cost: float | None = None
    current_tariff: str | None = None
    current_tariff_rate: float | None = None
    tariff_currency: str | None = None
