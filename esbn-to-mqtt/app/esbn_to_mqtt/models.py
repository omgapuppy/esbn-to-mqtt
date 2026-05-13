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
    processed_intervals: set[str] = field(default_factory=set)
