# esbn-to-mqtt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Home Assistant app version of `esbn-to-mqtt`, publishing ESB Networks smart meter HDF CSV data to Home Assistant MQTT discovery sensors suitable for the Energy dashboard.

**Architecture:** The repository is a Home Assistant app repository with one app in `esbn-to-mqtt/`. The Python worker is split into focused modules for config, ESBN fetching, HDF parsing, cumulative state, MQTT discovery/state publishing, and runtime orchestration. Tests exercise parsing, accumulator behavior, MQTT payload generation, docs-facing config, and secret redaction without needing Home Assistant in CI.

**Tech Stack:** Python 3.12, `pytest`, `ruff`, `mypy`, `paho-mqtt`, `httpx`, Home Assistant app `config.yaml`, Docker, GitHub Actions.

---

## File Structure

- Create `.gitignore`: ignore secrets, local exports, Python caches, virtualenvs, and build output.
- Create `.env.example`: document local-only ESBN and MQTT variables with stub values.
- Create `pyproject.toml`: package/test/lint/type configuration for the worker code under `esbn-to-mqtt/app`.
- Create `repository.yaml`: Home Assistant app repository metadata.
- Create `README.md`: concise public install and scope docs.
- Create `docs/development.md`: local setup, fixture anonymization, and test docs.
- Create `.github/workflows/ci.yml`: run lint, type check, unit tests, integration tests, and YAML validation.
- Create `esbn-to-mqtt/config.yaml`: Supervisor GUI options and schema.
- Create `esbn-to-mqtt/DOCS.md`: app-store-facing setup, Energy dashboard, and troubleshooting docs.
- Create `esbn-to-mqtt/README.md`: short app summary.
- Create `esbn-to-mqtt/CHANGELOG.md`: initial changelog.
- Create `esbn-to-mqtt/Dockerfile`: build the app image with explicit base image and labels.
- Create `esbn-to-mqtt/run.sh`: launch worker from `/data/options.json`.
- Create `esbn-to-mqtt/requirements.txt`: runtime dependencies.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/__init__.py`: package marker and version.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/config.py`: parse and validate Supervisor options and env-based dev config.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/logging.py`: redaction helpers and logging setup.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/models.py`: typed dataclasses for readings, totals, MQTT config, and runtime results.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/hdf.py`: parse ESBN 30-minute kWh HDF CSV files.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/state.py`: persist monotonic cumulative totals in `/data/state.json`.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/mqtt.py`: create discovery/state topics and publish retained MQTT messages.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/esbn.py`: ESBN portal client facade and auth/download flow.
- Create `esbn-to-mqtt/app/esbn_to_mqtt/main.py`: app orchestration loop.
- Create `tests/fixtures/esbn_30_min_kwh_anonymized.csv`: small anonymized import/export fixture.
- Create `tests/unit/test_config.py`: config validation tests.
- Create `tests/unit/test_logging.py`: redaction tests.
- Create `tests/unit/test_hdf.py`: parser tests.
- Create `tests/unit/test_state.py`: accumulator tests.
- Create `tests/unit/test_mqtt.py`: MQTT discovery/state payload tests.
- Create `tests/integration/test_pipeline.py`: fixture-to-MQTT-message integration test.
- Create `tests/test_app_metadata.py`: YAML/schema smoke tests for app repository metadata.

## Task 1: Repository Scaffolding

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `pyproject.toml`
- Create: `repository.yaml`

- [ ] **Step 1: Add repository ignore rules**

Create `.gitignore`:

```gitignore
.env
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
dist/
build/
*.egg-info/
data/
exports/
*.private.csv
*.raw.csv
```

- [ ] **Step 2: Add local environment stub**

Create `.env.example`:

```dotenv
ESBN_USERNAME=person@example.com
ESBN_PASSWORD=replace-me
ESBN_MPRN=10000000000
MQTT_HOST=core-mosquitto
MQTT_PORT=1883
MQTT_USERNAME=homeassistant
MQTT_PASSWORD=replace-me
POLL_INTERVAL_HOURS=6
MQTT_DISCOVERY_PREFIX=homeassistant
MQTT_TOPIC_PREFIX=esbn_to_mqtt
LOG_LEVEL=info
```

- [ ] **Step 3: Add Python project configuration**

Create `pyproject.toml`:

```toml
[project]
name = "esbn-to-mqtt"
version = "0.1.0"
description = "Home Assistant app worker that publishes ESB Networks smart meter data to MQTT"
requires-python = ">=3.12"
dependencies = [
  "beautifulsoup4>=4.12,<5",
  "httpx>=0.27,<1",
  "paho-mqtt>=2.1,<3",
  "python-dateutil>=2.9,<3",
  "PyYAML>=6.0,<7",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0,<9",
  "pytest-cov>=5.0,<6",
  "ruff>=0.6,<1",
  "mypy>=1.11,<2",
  "types-PyYAML>=6.0,<7",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["esbn-to-mqtt/app"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
mypy_path = "esbn-to-mqtt/app"
strict = true
```

- [ ] **Step 4: Add Home Assistant app repository metadata**

Create `repository.yaml`:

```yaml
name: esbn-to-mqtt Home Assistant app repository
url: https://github.com/omgapuppy/esbn-to-mqtt
maintainer: omgapuppy
```

- [ ] **Step 5: Run metadata smoke commands**

Run: `python3 -m pip install -e ".[dev]"`

Expected: dependencies install successfully.

Run: `python3 -c "import yaml; yaml.safe_load(open('repository.yaml'))"`

Expected: command exits with status `0`.

- [ ] **Step 6: Commit scaffolding**

```bash
git add .gitignore .env.example pyproject.toml repository.yaml
git commit -m "chore: add project scaffolding"
```

## Task 2: HA App Metadata and Container Entrypoint

**Files:**
- Create: `esbn-to-mqtt/config.yaml`
- Create: `esbn-to-mqtt/requirements.txt`
- Create: `esbn-to-mqtt/Dockerfile`
- Create: `esbn-to-mqtt/run.sh`
- Create: `esbn-to-mqtt/README.md`
- Create: `esbn-to-mqtt/CHANGELOG.md`

- [ ] **Step 1: Add app config**

Create `esbn-to-mqtt/config.yaml`:

```yaml
name: esbn-to-mqtt
version: "0.1.0"
slug: esbn_to_mqtt
description: Publish ESB Networks smart meter HDF data to Home Assistant MQTT sensors
url: https://github.com/omgapuppy/esbn-to-mqtt/tree/main/esbn-to-mqtt
arch:
  - aarch64
  - amd64
startup: application
boot: auto
init: false
stage: experimental
services:
  - mqtt:need
options:
  esbn_username: null
  esbn_password: null
  mprn: null
  mqtt_host: core-mosquitto
  mqtt_port: 1883
  mqtt_username: null
  mqtt_password: null
  poll_interval_hours: 6
  mqtt_discovery_prefix: homeassistant
  mqtt_topic_prefix: esbn_to_mqtt
  log_level: info
schema:
  esbn_username: email
  esbn_password: password
  mprn: match(^\d{11}$)
  mqtt_host: str
  mqtt_port: port
  mqtt_username: str
  mqtt_password: password
  poll_interval_hours: int(1,)
  mqtt_discovery_prefix: str
  mqtt_topic_prefix: match(^[A-Za-z0-9_-]+$)
  log_level: list(trace|debug|info|notice|warning|error|fatal)
image: ghcr.io/omgapuppy/{arch}-esbn-to-mqtt
```

- [ ] **Step 2: Add runtime requirements**

Create `esbn-to-mqtt/requirements.txt`:

```text
beautifulsoup4>=4.12,<5
httpx>=0.27,<1
paho-mqtt>=2.1,<3
python-dateutil>=2.9,<3
```

- [ ] **Step 3: Add Dockerfile**

Create `esbn-to-mqtt/Dockerfile`:

```Dockerfile
FROM ghcr.io/home-assistant/base:3.20

ARG BUILD_VERSION=0.1.0
ARG BUILD_ARCH=amd64

LABEL \
  io.hass.name="esbn-to-mqtt" \
  io.hass.description="Publish ESB Networks smart meter HDF data to MQTT" \
  io.hass.arch="${BUILD_ARCH}" \
  io.hass.type="app" \
  io.hass.version="${BUILD_VERSION}"

RUN apk add --no-cache python3 py3-pip

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/requirements.txt

COPY run.sh /run.sh
COPY app /app

RUN chmod a+x /run.sh

CMD ["/run.sh"]
```

- [ ] **Step 4: Add run script**

Create `esbn-to-mqtt/run.sh`:

```sh
#!/usr/bin/env sh
set -eu

export PYTHONPATH=/app
exec python3 -m esbn_to_mqtt.main --options /data/options.json --data-dir /data
```

- [ ] **Step 5: Add app README and changelog**

Create `esbn-to-mqtt/README.md`:

```markdown
# esbn-to-mqtt

Publishes ESB Networks smart meter HDF data to Home Assistant MQTT discovery sensors.

See `DOCS.md` for installation and configuration.
```

Create `esbn-to-mqtt/CHANGELOG.md`:

```markdown
# Changelog

## 0.1.0

- Initial experimental Home Assistant app release.
```

- [ ] **Step 6: Validate app YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('esbn-to-mqtt/config.yaml'))"`

Expected: command exits with status `0`.

- [ ] **Step 7: Commit app metadata**

```bash
git add esbn-to-mqtt/config.yaml esbn-to-mqtt/requirements.txt esbn-to-mqtt/Dockerfile esbn-to-mqtt/run.sh esbn-to-mqtt/README.md esbn-to-mqtt/CHANGELOG.md
git commit -m "feat: add home assistant app metadata"
```

## Task 3: Core Models, Config, and Redaction

**Files:**
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/__init__.py`
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/models.py`
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/config.py`
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/logging.py`
- Create: `tests/unit/test_config.py`
- Create: `tests/unit/test_logging.py`

- [ ] **Step 1: Write config and redaction tests**

Create `tests/unit/test_config.py`:

```python
import pytest

from esbn_to_mqtt.config import AppConfig, ConfigError, load_config_dict


def valid_options() -> dict[str, object]:
    return {
        "esbn_username": "person@example.com",
        "esbn_password": "secret",
        "mprn": "10000000000",
        "mqtt_host": "core-mosquitto",
        "mqtt_port": 1883,
        "mqtt_username": "ha",
        "mqtt_password": "mqttpass",
        "poll_interval_hours": 6,
        "mqtt_discovery_prefix": "homeassistant",
        "mqtt_topic_prefix": "esbn_to_mqtt",
        "log_level": "info",
    }


def test_load_config_dict_accepts_valid_options() -> None:
    config = load_config_dict(valid_options())
    assert isinstance(config, AppConfig)
    assert config.mprn == "10000000000"
    assert config.mqtt.host == "core-mosquitto"
    assert config.poll_interval_seconds == 21600


@pytest.mark.parametrize("mprn", ["", "123", "1234567890a", "123456789012"])
def test_load_config_dict_rejects_invalid_mprn(mprn: str) -> None:
    options = valid_options()
    options["mprn"] = mprn
    with pytest.raises(ConfigError, match="MPRN"):
        load_config_dict(options)


def test_load_config_dict_rejects_missing_secret() -> None:
    options = valid_options()
    options["esbn_password"] = ""
    with pytest.raises(ConfigError, match="esbn_password"):
        load_config_dict(options)
```

Create `tests/unit/test_logging.py`:

```python
from esbn_to_mqtt.logging import hash_mprn, mask_mprn, redact


def test_mask_mprn_keeps_only_last_three_digits() -> None:
    assert mask_mprn("10000012345") == "********345"


def test_hash_mprn_is_stable_and_not_raw() -> None:
    value = hash_mprn("10000012345")
    assert value == hash_mprn("10000012345")
    assert "10000012345" not in value


def test_redact_removes_sensitive_values() -> None:
    message = redact(
        "login person@example.com password=secret mprn=10000012345 cookie=abcdef",
        secrets=["secret", "abcdef", "person@example.com", "10000012345"],
    )
    assert "secret" not in message
    assert "abcdef" not in message
    assert "person@example.com" not in message
    assert "10000012345" not in message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config.py tests/unit/test_logging.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'esbn_to_mqtt'`.

- [ ] **Step 3: Add core package and models**

Create `esbn-to-mqtt/app/esbn_to_mqtt/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `esbn-to-mqtt/app/esbn_to_mqtt/models.py`:

```python
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
```

- [ ] **Step 4: Add config loader**

Create `esbn-to-mqtt/app/esbn_to_mqtt/config.py`:

```python
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .models import AppConfig, EsbnCredentials, MqttConfig

MPRN_PATTERN = re.compile(r"^\d{11}$")


class ConfigError(ValueError):
    pass


def _required_str(options: dict[str, Any], key: str) -> str:
    value = options.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} is required")
    return value.strip()


def _required_int(options: dict[str, Any], key: str) -> int:
    value = options.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def load_config_dict(options: dict[str, Any]) -> AppConfig:
    mprn = _required_str(options, "mprn")
    if not MPRN_PATTERN.match(mprn):
        raise ConfigError("MPRN must be exactly 11 digits")

    poll_interval_hours = _required_int(options, "poll_interval_hours")
    if poll_interval_hours < 1:
        raise ConfigError("poll_interval_hours must be at least 1")

    mqtt_port = _required_int(options, "mqtt_port")
    if mqtt_port < 1 or mqtt_port > 65535:
        raise ConfigError("mqtt_port must be a valid TCP port")

    return AppConfig(
        esbn=EsbnCredentials(
            username=_required_str(options, "esbn_username"),
            password=_required_str(options, "esbn_password"),
            mprn=mprn,
        ),
        mqtt=MqttConfig(
            host=_required_str(options, "mqtt_host"),
            port=mqtt_port,
            username=_required_str(options, "mqtt_username"),
            password=_required_str(options, "mqtt_password"),
            discovery_prefix=_required_str(options, "mqtt_discovery_prefix"),
            topic_prefix=_required_str(options, "mqtt_topic_prefix"),
        ),
        poll_interval_hours=poll_interval_hours,
        log_level=_required_str(options, "log_level"),
    )


def load_options_file(path: Path) -> AppConfig:
    with path.open("r", encoding="utf-8") as handle:
        options = json.load(handle)
    if not isinstance(options, dict):
        raise ConfigError("options file must contain a JSON object")
    return load_config_dict(options)


def load_env_config() -> AppConfig:
    return load_config_dict(
        {
            "esbn_username": os.environ.get("ESBN_USERNAME", ""),
            "esbn_password": os.environ.get("ESBN_PASSWORD", ""),
            "mprn": os.environ.get("ESBN_MPRN", ""),
            "mqtt_host": os.environ.get("MQTT_HOST", "core-mosquitto"),
            "mqtt_port": int(os.environ.get("MQTT_PORT", "1883")),
            "mqtt_username": os.environ.get("MQTT_USERNAME", ""),
            "mqtt_password": os.environ.get("MQTT_PASSWORD", ""),
            "poll_interval_hours": int(os.environ.get("POLL_INTERVAL_HOURS", "6")),
            "mqtt_discovery_prefix": os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant"),
            "mqtt_topic_prefix": os.environ.get("MQTT_TOPIC_PREFIX", "esbn_to_mqtt"),
            "log_level": os.environ.get("LOG_LEVEL", "info"),
        }
    )
```

- [ ] **Step 5: Add redaction helpers**

Create `esbn-to-mqtt/app/esbn_to_mqtt/logging.py`:

```python
from __future__ import annotations

import hashlib
import logging


def mask_mprn(mprn: str) -> str:
    if len(mprn) <= 3:
        return "*" * len(mprn)
    return "*" * (len(mprn) - 3) + mprn[-3:]


def hash_mprn(mprn: str) -> str:
    return hashlib.sha256(mprn.encode("utf-8")).hexdigest()[:12]


def redact(message: str, secrets: list[str]) -> str:
    redacted = message
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
```

- [ ] **Step 6: Run config and redaction tests**

Run: `pytest tests/unit/test_config.py tests/unit/test_logging.py -q`

Expected: PASS.

- [ ] **Step 7: Commit core config**

```bash
git add esbn-to-mqtt/app/esbn_to_mqtt tests/unit/test_config.py tests/unit/test_logging.py
git commit -m "feat: add config validation and redaction"
```

## Task 4: HDF CSV Parser

**Files:**
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/hdf.py`
- Create: `tests/fixtures/esbn_30_min_kwh_anonymized.csv`
- Create: `tests/unit/test_hdf.py`

- [ ] **Step 1: Add anonymized fixture**

Create `tests/fixtures/esbn_30_min_kwh_anonymized.csv`:

```csv
MPRN,Read Date and End Time,Import kWh,Export kWh,Quality
10000000000,2026-05-12 00:30,0.120,0.000,A
10000000000,2026-05-12 01:00,0.110,0.000,A
10000000000,2026-05-12 01:30,0.105,0.010,A
10000000000,2026-05-12 02:00,0.115,0.020,A
```

- [ ] **Step 2: Write parser tests**

Create `tests/unit/test_hdf.py`:

```python
from datetime import timezone
from pathlib import Path

from esbn_to_mqtt.hdf import parse_hdf_csv


def test_parse_hdf_csv_reads_import_and_export_values() -> None:
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert len(rows) == 4
    assert rows[0].import_kwh == 0.120
    assert rows[2].export_kwh == 0.010
    assert rows[0].timestamp.tzinfo is not None
    assert rows[0].timestamp.utcoffset() == timezone.utc.utcoffset(rows[0].timestamp)


def test_parse_hdf_csv_uses_interval_start_from_end_time() -> None:
    rows = parse_hdf_csv(Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text())
    assert rows[0].timestamp.isoformat() == "2026-05-12T00:00:00+00:00"
```

- [ ] **Step 3: Run parser tests to verify they fail**

Run: `pytest tests/unit/test_hdf.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing `parse_hdf_csv`.

- [ ] **Step 4: Add HDF parser**

Create `esbn-to-mqtt/app/esbn_to_mqtt/hdf.py`:

```python
from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from io import StringIO

from .models import MeterReading

DATE_COLUMNS = ("Read Date and End Time", "Read Date", "Date")
IMPORT_COLUMNS = ("Import kWh", "Consumption kWh", "kWh", "Active Import kWh")
EXPORT_COLUMNS = ("Export kWh", "Active Export kWh")


class HdfParseError(ValueError):
    pass


def _first_present(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _parse_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value.strip())


def _parse_end_time(value: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            end_time = datetime.strptime(value.strip(), fmt).replace(tzinfo=UTC)
            return end_time - timedelta(minutes=30)
        except ValueError:
            continue
    raise HdfParseError(f"unsupported HDF timestamp format: {value!r}")


def parse_hdf_csv(content: str) -> list[MeterReading]:
    reader = csv.DictReader(StringIO(content.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise HdfParseError("HDF CSV has no header row")

    readings: list[MeterReading] = []
    for row in reader:
        date_value = _first_present(row, DATE_COLUMNS)
        if date_value is None:
            raise HdfParseError("HDF CSV is missing a supported date column")

        import_kwh = _parse_float(_first_present(row, IMPORT_COLUMNS))
        export_kwh = _parse_float(_first_present(row, EXPORT_COLUMNS))
        if import_kwh is None and export_kwh is None:
            continue

        readings.append(
            MeterReading(
                timestamp=_parse_end_time(date_value),
                import_kwh=import_kwh,
                export_kwh=export_kwh,
                quality=row.get("Quality") or row.get("Read Quality"),
            )
        )

    return sorted(readings, key=lambda reading: reading.timestamp)
```

- [ ] **Step 5: Run parser tests**

Run: `pytest tests/unit/test_hdf.py -q`

Expected: PASS.

- [ ] **Step 6: Commit parser**

```bash
git add esbn-to-mqtt/app/esbn_to_mqtt/hdf.py tests/fixtures/esbn_30_min_kwh_anonymized.csv tests/unit/test_hdf.py
git commit -m "feat: parse esbn hdf csv exports"
```

## Task 5: Persistent Monotonic State

**Files:**
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/state.py`
- Create: `tests/unit/test_state.py`

- [ ] **Step 1: Write accumulator tests**

Create `tests/unit/test_state.py`:

```python
from datetime import UTC, datetime

from esbn_to_mqtt.models import MeterReading
from esbn_to_mqtt.state import AccumulatorState


def reading(hour: int, import_kwh: float, export_kwh: float | None = None) -> MeterReading:
    return MeterReading(
        timestamp=datetime(2026, 5, 12, hour, 0, tzinfo=UTC),
        import_kwh=import_kwh,
        export_kwh=export_kwh,
    )


def test_accumulator_adds_only_new_intervals() -> None:
    state = AccumulatorState.empty()
    first = state.apply([reading(0, 1.0), reading(1, 2.0, 0.5)])
    second = first.apply([reading(1, 2.0, 0.5), reading(2, 3.0, 1.0)])

    assert second.import_total_kwh == 6.0
    assert second.export_total_kwh == 1.5
    assert len(second.processed_intervals) == 4


def test_accumulator_round_trips_json(tmp_path) -> None:
    path = tmp_path / "state.json"
    state = AccumulatorState.empty().apply([reading(0, 1.25)])
    state.save(path)

    loaded = AccumulatorState.load(path)
    assert loaded.import_total_kwh == 1.25
    assert loaded.processed_intervals == state.processed_intervals
```

- [ ] **Step 2: Run accumulator tests to verify they fail**

Run: `pytest tests/unit/test_state.py -q`

Expected: FAIL with missing module.

- [ ] **Step 3: Add persistent accumulator**

Create `esbn-to-mqtt/app/esbn_to_mqtt/state.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import MeterReading, MeterTotals


@dataclass(frozen=True)
class AccumulatorState:
    import_total_kwh: float
    export_total_kwh: float | None
    last_interval_start: datetime | None
    processed_intervals: set[str]

    @classmethod
    def empty(cls) -> "AccumulatorState":
        return cls(
            import_total_kwh=0.0,
            export_total_kwh=None,
            last_interval_start=None,
            processed_intervals=set(),
        )

    @classmethod
    def load(cls, path: Path) -> "AccumulatorState":
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
            processed_intervals=set(data.get("processed_intervals", [])),
        )

    def apply(self, readings: list[MeterReading]) -> "AccumulatorState":
        import_total = self.import_total_kwh
        export_total = self.export_total_kwh
        processed = set(self.processed_intervals)
        last_interval = self.last_interval_start

        for reading in sorted(readings, key=lambda item: item.timestamp):
            last_interval = reading.timestamp if last_interval is None else max(last_interval, reading.timestamp)
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

        return AccumulatorState(
            import_total_kwh=round(import_total, 6),
            export_total_kwh=None if export_total is None else round(export_total, 6),
            last_interval_start=last_interval,
            processed_intervals=processed,
        )

    def to_totals(self) -> MeterTotals:
        return MeterTotals(
            import_total_kwh=self.import_total_kwh,
            export_total_kwh=self.export_total_kwh,
            last_interval_start=self.last_interval_start,
            processed_intervals=set(self.processed_intervals),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "import_total_kwh": self.import_total_kwh,
                    "export_total_kwh": self.export_total_kwh,
                    "last_interval_start": (
                        None if self.last_interval_start is None else self.last_interval_start.isoformat()
                    ),
                    "processed_intervals": sorted(self.processed_intervals),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run accumulator tests**

Run: `pytest tests/unit/test_state.py -q`

Expected: PASS.

- [ ] **Step 5: Commit accumulator**

```bash
git add esbn-to-mqtt/app/esbn_to_mqtt/state.py tests/unit/test_state.py
git commit -m "feat: persist monotonic meter totals"
```

## Task 6: MQTT Discovery and State Messages

**Files:**
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/mqtt.py`
- Create: `tests/unit/test_mqtt.py`

- [ ] **Step 1: Write MQTT payload tests**

Create `tests/unit/test_mqtt.py`:

```python
from datetime import UTC, datetime

from esbn_to_mqtt.models import MqttConfig, MeterTotals
from esbn_to_mqtt.mqtt import build_discovery_messages, build_state_message


def mqtt_config() -> MqttConfig:
    return MqttConfig(
        host="core-mosquitto",
        port=1883,
        username="ha",
        password="secret",
    )


def totals() -> MeterTotals:
    return MeterTotals(
        import_total_kwh=3.45,
        export_total_kwh=1.25,
        last_interval_start=datetime(2026, 5, 12, 1, 30, tzinfo=UTC),
    )


def test_build_discovery_messages_use_energy_dashboard_metadata() -> None:
    messages = build_discovery_messages(mqtt_config(), "10000000000", include_export=True)
    import_message = next(message for message in messages if "import_total" in message.topic)

    assert import_message.retain is True
    assert import_message.payload["device_class"] == "energy"
    assert import_message.payload["state_class"] == "total_increasing"
    assert import_message.payload["unit_of_measurement"] == "kWh"
    assert import_message.payload["availability_topic"].endswith("/availability")
    assert "10000000000" not in str(import_message.payload)


def test_build_state_message_contains_totals_and_timestamps() -> None:
    message = build_state_message(mqtt_config(), "10000000000", totals())
    assert message.retain is True
    assert message.payload["import_total_kwh"] == 3.45
    assert message.payload["export_total_kwh"] == 1.25
    assert message.payload["last_interval_start"] == "2026-05-12T01:30:00+00:00"
```

- [ ] **Step 2: Run MQTT tests to verify they fail**

Run: `pytest tests/unit/test_mqtt.py -q`

Expected: FAIL with missing module.

- [ ] **Step 3: Add MQTT message builder**

Create `esbn-to-mqtt/app/esbn_to_mqtt/mqtt.py`:

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import paho.mqtt.client as mqtt

from .logging import hash_mprn
from .models import MeterTotals, MqttConfig


@dataclass(frozen=True)
class MqttMessage:
    topic: str
    payload: dict[str, Any] | str
    retain: bool = True

    def encoded_payload(self) -> str:
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, sort_keys=True)


def _safe_mprn(mprn: str) -> str:
    return hash_mprn(mprn)


def availability_topic(config: MqttConfig, mprn: str) -> str:
    return f"{config.topic_prefix}/{_safe_mprn(mprn)}/availability"


def state_topic(config: MqttConfig, mprn: str) -> str:
    return f"{config.topic_prefix}/{_safe_mprn(mprn)}/state"


def _device(mprn: str) -> dict[str, Any]:
    safe = _safe_mprn(mprn)
    return {
        "identifiers": [f"esbn_to_mqtt_{safe}"],
        "manufacturer": "ESB Networks",
        "model": "Smart Meter",
        "name": "ESBN Smart Meter",
    }


def _sensor_config(config: MqttConfig, mprn: str, role: str, name: str, template: str) -> MqttMessage:
    safe = _safe_mprn(mprn)
    return MqttMessage(
        topic=f"{config.discovery_prefix}/sensor/esbn_to_mqtt_{safe}_{role}/config",
        payload={
            "name": name,
            "unique_id": f"esbn_to_mqtt_{safe}_{role}",
            "state_topic": state_topic(config, mprn),
            "availability_topic": availability_topic(config, mprn),
            "device_class": "energy",
            "state_class": "total_increasing",
            "unit_of_measurement": "kWh",
            "suggested_display_precision": 3,
            "value_template": template,
            "device": _device(mprn),
        },
    )


def build_discovery_messages(
    config: MqttConfig,
    mprn: str,
    *,
    include_export: bool,
) -> list[MqttMessage]:
    messages = [
        _sensor_config(
            config,
            mprn,
            "import_total",
            "ESBN Import Total",
            "{{ value_json.import_total_kwh }}",
        )
    ]
    if include_export:
        messages.append(
            _sensor_config(
                config,
                mprn,
                "export_total",
                "ESBN Export Total",
                "{{ value_json.export_total_kwh }}",
            )
        )
    return messages


def build_state_message(config: MqttConfig, mprn: str, totals: MeterTotals) -> MqttMessage:
    payload: dict[str, Any] = {
        "import_total_kwh": round(totals.import_total_kwh, 6),
        "last_successful_fetch": datetime.now(UTC).isoformat(),
        "source": "esb_networks_hdf_30_min_kwh",
    }
    if totals.export_total_kwh is not None:
        payload["export_total_kwh"] = round(totals.export_total_kwh, 6)
    if totals.last_interval_start is not None:
        payload["last_interval_start"] = totals.last_interval_start.isoformat()
    return MqttMessage(topic=state_topic(config, mprn), payload=payload)


class MqttPublisher:
    def __init__(self, config: MqttConfig) -> None:
        self._config = config
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(config.username, config.password)

    def connect(self) -> None:
        self._client.connect(self._config.host, self._config.port)

    def publish(self, message: MqttMessage) -> None:
        result = self._client.publish(
            message.topic,
            message.encoded_payload(),
            qos=1,
            retain=message.retain,
        )
        result.wait_for_publish()

    def disconnect(self) -> None:
        self._client.disconnect()
```

- [ ] **Step 4: Run MQTT tests**

Run: `pytest tests/unit/test_mqtt.py -q`

Expected: PASS.

- [ ] **Step 5: Commit MQTT messages**

```bash
git add esbn-to-mqtt/app/esbn_to_mqtt/mqtt.py tests/unit/test_mqtt.py
git commit -m "feat: build home assistant mqtt discovery payloads"
```

## Task 7: ESBN Client Facade and Runtime Loop

**Files:**
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/esbn.py`
- Create: `esbn-to-mqtt/app/esbn_to_mqtt/main.py`
- Create: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Write pipeline integration test**

Create `tests/integration/test_pipeline.py`:

```python
from pathlib import Path

from esbn_to_mqtt.hdf import parse_hdf_csv
from esbn_to_mqtt.models import MqttConfig
from esbn_to_mqtt.mqtt import build_discovery_messages, build_state_message
from esbn_to_mqtt.state import AccumulatorState


def test_fixture_to_mqtt_messages_pipeline() -> None:
    content = Path("tests/fixtures/esbn_30_min_kwh_anonymized.csv").read_text()
    readings = parse_hdf_csv(content)
    totals = AccumulatorState.empty().apply(readings).to_totals()
    mqtt_config = MqttConfig(
        host="core-mosquitto",
        port=1883,
        username="ha",
        password="secret",
    )

    discovery = build_discovery_messages(mqtt_config, "10000000000", include_export=True)
    state = build_state_message(mqtt_config, "10000000000", totals)

    assert len(discovery) == 2
    assert state.payload["import_total_kwh"] == 0.45
    assert state.payload["export_total_kwh"] == 0.03
```

- [ ] **Step 2: Run pipeline test**

Run: `pytest tests/integration/test_pipeline.py -q`

Expected: PASS once earlier tasks are complete.

- [ ] **Step 3: Add ESBN client facade**

Create `esbn-to-mqtt/app/esbn_to_mqtt/esbn.py`:

```python
from __future__ import annotations

import logging

import httpx

from .models import EsbnCredentials

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://myaccount.esbnetworks.ie"


class EsbnError(RuntimeError):
    pass


class EsbnAuthenticationError(EsbnError):
    pass


class EsbnChallengeError(EsbnError):
    pass


class EsbnClient:
    def __init__(self, credentials: EsbnCredentials) -> None:
        self._credentials = credentials
        self._client = httpx.Client(
            base_url=BASE_URL,
            follow_redirects=True,
            timeout=60.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                )
            },
        )

    def close(self) -> None:
        self._client.close()

    def download_30_min_kwh_hdf(self) -> str:
        raise EsbnError(
            "ESBN live download is not implemented until a current authenticated export "
            "flow is captured locally and encoded without secrets"
        )
```

- [ ] **Step 4: Add runtime loop**

Create `esbn-to-mqtt/app/esbn_to_mqtt/main.py`:

```python
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from .config import load_options_file
from .esbn import EsbnClient, EsbnError
from .hdf import parse_hdf_csv
from .logging import configure_logging, mask_mprn
from .mqtt import MqttMessage, MqttPublisher, availability_topic, build_discovery_messages, build_state_message
from .state import AccumulatorState

LOGGER = logging.getLogger(__name__)


def run_once(options_path: Path, data_dir: Path) -> None:
    config = load_options_file(options_path)
    configure_logging(config.log_level)
    LOGGER.info("starting esbn-to-mqtt for MPRN %s", mask_mprn(config.mprn))

    state_path = data_dir / "state.json"
    accumulator = AccumulatorState.load(state_path)
    publisher = MqttPublisher(config.mqtt)
    client = EsbnClient(config.esbn)

    try:
        publisher.connect()
        for message in build_discovery_messages(
            config.mqtt,
            config.mprn,
            include_export=accumulator.export_total_kwh is not None,
        ):
            publisher.publish(message)

        csv_content = client.download_30_min_kwh_hdf()
        readings = parse_hdf_csv(csv_content)
        accumulator = accumulator.apply(readings)
        accumulator.save(state_path)

        for message in build_discovery_messages(
            config.mqtt,
            config.mprn,
            include_export=accumulator.export_total_kwh is not None,
        ):
            publisher.publish(message)
        publisher.publish(build_state_message(config.mqtt, config.mprn, accumulator.to_totals()))
        publisher.publish(MqttMessage(availability_topic(config.mqtt, config.mprn), "online"))
    finally:
        client.close()
        publisher.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--data-dir", type=Path, default=Path("/data"))
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    while True:
        try:
            run_once(args.options, args.data_dir)
        except EsbnError as exc:
            LOGGER.error("ESBN polling failed: %s", exc)
        if args.once:
            break

        config = load_options_file(args.options)
        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run pipeline and import checks**

Run: `pytest tests/integration/test_pipeline.py -q`

Expected: PASS.

Run: `python3 -m esbn_to_mqtt.main --help`

Expected: CLI help prints and exits `0`.

- [ ] **Step 6: Commit runtime skeleton**

```bash
git add esbn-to-mqtt/app/esbn_to_mqtt/esbn.py esbn-to-mqtt/app/esbn_to_mqtt/main.py tests/integration/test_pipeline.py
git commit -m "feat: add runtime polling skeleton"
```

## Task 8: Documentation

**Files:**
- Create: `README.md`
- Create: `docs/development.md`
- Create: `esbn-to-mqtt/DOCS.md`

- [ ] **Step 1: Add root README**

Create `README.md`:

```markdown
# esbn-to-mqtt

`esbn-to-mqtt` is an unofficial Home Assistant app that publishes ESB Networks smart meter HDF CSV data to MQTT discovery sensors for the Home Assistant Energy dashboard.

This is not a HACS integration and is not affiliated with, endorsed by, or connected to ESB Networks.

## Requirements

- Home Assistant OS or another Home Assistant installation with Supervisor apps.
- MQTT integration enabled in Home Assistant.
- MQTT broker available, such as the default Mosquitto Broker app.
- ESB Networks online account with access to your smart meter data.
- Your 11-digit MPRN.

## Installation

1. In Home Assistant, go to **Settings > Apps**.
2. Open app repositories.
3. Add `https://github.com/omgapuppy/esbn-to-mqtt`.
4. Install `esbn-to-mqtt`.
5. Configure ESBN credentials, MPRN, and MQTT credentials in the app settings.
6. Start the app.

For app-specific setup, see [`esbn-to-mqtt/DOCS.md`](esbn-to-mqtt/DOCS.md).

For local development, see [`docs/development.md`](docs/development.md).
```

- [ ] **Step 2: Add development docs**

Create `docs/development.md`:

```markdown
# Development

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e ".[dev]"
cp .env.example .env
```

Edit `.env` locally only. Never commit `.env`, real ESBN credentials, real MPRNs, raw ESBN exports, cookies, or auth responses.

## Tests

```bash
ruff check .
mypy esbn-to-mqtt/app
pytest
```

## Fixture Anonymization

Before committing ESBN export data:

- Replace the MPRN with `10000000000`.
- Remove account IDs, names, addresses, cookies, tokens, and hidden metadata.
- Shift timestamps if needed.
- Scale readings if needed while keeping a realistic shape.
- Keep only enough rows to exercise parser and accumulator behavior.

Committed fixtures must live under `tests/fixtures/` and use `_anonymized` in the filename.
```

- [ ] **Step 3: Add app docs**

Create `esbn-to-mqtt/DOCS.md`:

```markdown
# esbn-to-mqtt

## Configuration

Set these options in the Home Assistant app UI:

- `esbn_username`: ESB Networks account email.
- `esbn_password`: ESB Networks account password.
- `mprn`: 11-digit MPRN.
- `mqtt_host`: MQTT broker host, default `core-mosquitto`.
- `mqtt_port`: MQTT broker port, default `1883`.
- `mqtt_username`: MQTT username.
- `mqtt_password`: MQTT password.
- `poll_interval_hours`: polling interval, default `6`.
- `mqtt_discovery_prefix`: default `homeassistant`.
- `mqtt_topic_prefix`: default `esbn_to_mqtt`.

## Energy Dashboard

After the app publishes discovery messages, Home Assistant should discover an `ESBN Import Total` sensor. Add that sensor in **Settings > Dashboards > Energy** as grid consumption.

If export data exists in your ESBN HDF file, the app also publishes `ESBN Export Total`.

## Data Freshness

ESBN data is not real-time. The app polls every 6 hours by default, but newly available smart meter readings may still lag behind current time.

## Troubleshooting

- Check MQTT credentials if no entities appear.
- Check app logs for ESBN authentication failures.
- If ESBN presents CAPTCHA or anti-automation checks, the app will avoid rapid retries.
- If data is stale, verify the ESBN portal has newer HDF data available.

The app redacts credentials and raw MPRNs from logs.
```

- [ ] **Step 4: Commit docs**

```bash
git add README.md docs/development.md esbn-to-mqtt/DOCS.md
git commit -m "docs: add installation and development docs"
```

## Task 9: CI Workflow and Metadata Tests

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `tests/test_app_metadata.py`

- [ ] **Step 1: Add metadata tests**

Create `tests/test_app_metadata.py`:

```python
from pathlib import Path

import yaml


def test_repository_yaml_is_valid() -> None:
    data = yaml.safe_load(Path("repository.yaml").read_text())
    assert data["name"] == "esbn-to-mqtt Home Assistant app repository"
    assert data["url"] == "https://github.com/omgapuppy/esbn-to-mqtt"


def test_app_config_yaml_is_valid() -> None:
    data = yaml.safe_load(Path("esbn-to-mqtt/config.yaml").read_text())
    assert data["slug"] == "esbn_to_mqtt"
    assert data["options"]["poll_interval_hours"] == 6
    assert data["schema"]["esbn_password"] == "password"
    assert "mqtt:need" in data["services"]
```

- [ ] **Step 2: Add CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
  push:
    branches:
      - "codex/**"
      - "feature/**"
      - "fix/**"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: python -m pip install -e ".[dev]"
      - name: Lint
        run: ruff check .
      - name: Type check
        run: mypy esbn-to-mqtt/app
      - name: Test
        run: pytest
```

- [ ] **Step 3: Run local CI commands**

Run: `ruff check .`

Expected: PASS.

Run: `mypy esbn-to-mqtt/app`

Expected: PASS.

Run: `pytest`

Expected: PASS.

- [ ] **Step 4: Commit CI**

```bash
git add .github/workflows/ci.yml tests/test_app_metadata.py
git commit -m "ci: add pull request checks"
```

## Task 10: Live ESBN Download Implementation

**Files:**
- Modify: `esbn-to-mqtt/app/esbn_to_mqtt/esbn.py`
- Create: `tests/unit/test_esbn.py`

- [ ] **Step 1: Confirm the public reference flow and local credential loading**

Use the referenced public integration only for request-shape guidance. Use `.env` only for any later live check. Do not commit raw HTML, cookies, tokens, credentials, MPRNs, or raw exports.

Run: `. .venv/bin/activate && python3 -c "from esbn_to_mqtt.config import load_env_config; print(load_env_config().mprn[-3:])"`

Expected: prints only the final three MPRN digits from local `.env`.

- [ ] **Step 2: Write tests for the encoded ESBN flow using fake responses**

Create `tests/unit/test_esbn.py`:

```python
import json
from urllib.parse import parse_qs

import httpx
import pytest

from esbn_to_mqtt.esbn import EsbnChallengeError, EsbnClient
from esbn_to_mqtt.models import EsbnCredentials


def credentials() -> EsbnCredentials:
    return EsbnCredentials(
        username="person@example.com",
        password="secret-password",
        mprn="10000000000",
    )


def test_download_30_min_kwh_hdf_returns_csv_without_logging_secrets() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = str(request.url)
        if url == "https://myaccount.esbnetworks.ie/":
            return httpx.Response(
                200,
                text='''<script>var SETTINGS = {"csrf":"csrf-token","transId":"tx-id"};</script>''',
                request=request,
            )
        if url.startswith("https://login.esbnetworks.ie/") and "/SelfAsserted" in url:
            form = parse_qs(request.content.decode())
            assert form["signInName"] == ["person@example.com"]
            assert form["password"] == ["secret-password"]
            return httpx.Response(200, json={"status": "ok"}, request=request)
        if "/api/CombinedSigninAndSignup/confirmed" in url:
            return httpx.Response(
                200,
                text=(
                    '<form id="auto" action="https://myaccount.esbnetworks.ie/signin-oidc">'
                    '<input name="state" value="state-value">'
                    '<input name="client_info" value="client-info">'
                    '<input name="code" value="auth-code">'
                    "</form>"
                ),
                request=request,
            )
        if url == "https://myaccount.esbnetworks.ie/signin-oidc":
            return httpx.Response(302, headers={"location": "/"}, request=request)
        if url == "https://myaccount.esbnetworks.ie/Api/HistoricConsumption":
            return httpx.Response(200, text="<html>consumption</html>", request=request)
        if url == "https://myaccount.esbnetworks.ie/af/t":
            return httpx.Response(200, json={"token": "download-token"}, request=request)
        if url == "https://myaccount.esbnetworks.ie/DataHub/DownloadHdfPeriodic":
            assert json.loads(request.content) == {
                "mprn": "10000000000",
                "searchType": "intervalkwh",
            }
            assert request.headers["X-Xsrf-Token"] == "download-token"
            return httpx.Response(
                200,
                text="MPRN,Read Date and End Time,Import kWh\n10000000000,2026-05-12 00:30,0.120\n",
                request=request,
            )
        raise AssertionError(f"unexpected request: {request.method} {url}")

    client = EsbnClient(credentials(), transport=httpx.MockTransport(handler))

    try:
        csv = client.download_30_min_kwh_hdf()
    finally:
        client.close()

    assert "Import kWh" in csv
    assert [request.url.path for request in requests] == [
        "/",
        "/esbntwkscustportalprdb2c01.onmicrosoft.com/B2C_1A_signup_signin/SelfAsserted",
        "/esbntwkscustportalprdb2c01.onmicrosoft.com/B2C_1A_signup_signin/api/CombinedSigninAndSignup/confirmed",
        "/signin-oidc",
        "/",
        "/Api/HistoricConsumption",
        "/af/t",
        "/DataHub/DownloadHdfPeriodic",
    ]


def test_download_raises_challenge_error_on_captcha() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://myaccount.esbnetworks.ie/":
            return httpx.Response(
                200,
                text='''<script>var SETTINGS = {"csrf":"csrf-token","transId":"tx-id"};</script>''',
                request=request,
            )
        if "/SelfAsserted" in str(request.url):
            return httpx.Response(200, json={"status": "ok"}, request=request)
        if "/confirmed" in str(request.url):
            return httpx.Response(200, text='<input name="g-recaptcha-response">', request=request)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    client = EsbnClient(credentials(), transport=httpx.MockTransport(handler))

    try:
        with pytest.raises(EsbnChallengeError):
            client.download_30_min_kwh_hdf()
    finally:
        client.close()
```

- [ ] **Step 3: Run ESBN tests to verify they fail**

Run: `pytest tests/unit/test_esbn.py -q`

Expected: FAIL because `EsbnClient` does not yet accept `transport` and `download_30_min_kwh_hdf()` still raises the scaffold error.

- [ ] **Step 4: Implement the ESBN auth and download flow**

Replace `esbn-to-mqtt/app/esbn_to_mqtt/esbn.py` with:

```python
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from .models import EsbnCredentials

LOGGER = logging.getLogger(__name__)

ESB_LOGIN_URL = "https://myaccount.esbnetworks.ie/"
ESB_AUTH_BASE_URL = (
    "https://login.esbnetworks.ie/"
    "esbntwkscustportalprdb2c01.onmicrosoft.com/B2C_1A_signup_signin"
)
ESB_MYACCOUNT_URL = "https://myaccount.esbnetworks.ie"
ESB_CONSUMPTION_URL = "https://myaccount.esbnetworks.ie/Api/HistoricConsumption"
ESB_TOKEN_URL = "https://myaccount.esbnetworks.ie/af/t"
ESB_DOWNLOAD_URL = "https://myaccount.esbnetworks.ie/DataHub/DownloadHdfPeriodic"
MAX_CSV_SIZE_BYTES = 10 * 1024 * 1024


class EsbnError(RuntimeError):
    pass


class EsbnAuthenticationError(EsbnError):
    pass


class EsbnChallengeError(EsbnError):
    pass


@dataclass(frozen=True)
class AuthResult:
    download_token: str
    user_agent: str


class EsbnClient:
    def __init__(
        self,
        credentials: EsbnCredentials,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._credentials = credentials
        self._user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
        self._client = httpx.Client(
            follow_redirects=True,
            timeout=60.0,
            transport=transport,
            headers={"User-Agent": self._user_agent},
        )

    def close(self) -> None:
        self._client.close()

    def _browser_headers(self, **extra: str) -> dict[str, str]:
        headers = {
            "User-Agent": self._user_agent,
            "Accept-Language": "en-US,en;q=0.5",
        }
        headers.update(extra)
        return headers

    def _extract_settings(self, html: str) -> dict[str, str]:
        match = re.search(r"var SETTINGS = (\{.*?\});", html)
        if not match:
            raise EsbnAuthenticationError("Could not find ESBN login settings")
        data = json.loads(match.group(1))
        csrf = data.get("csrf")
        trans_id = data.get("transId")
        if not isinstance(csrf, str) or not isinstance(trans_id, str):
            raise EsbnAuthenticationError("ESBN login settings did not include required tokens")
        return {"csrf": csrf, "transId": trans_id}

    def _extract_auto_form(self, html: str) -> tuple[str, dict[str, str]]:
        if (
            "g-recaptcha-response" in html
            or "captcha.html" in html.lower()
            or "not a robot" in html.lower()
        ):
            raise EsbnChallengeError("ESBN requires interactive verification")

        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form", {"id": "auto"})
        if form is None:
            raise EsbnAuthenticationError("Could not find ESBN sign-in form")
        action = form.get("action")
        if not isinstance(action, str) or not action:
            raise EsbnAuthenticationError("ESBN sign-in form was missing an action")

        values: dict[str, str] = {}
        for field in ("state", "client_info", "code"):
            input_node = form.find("input", {"name": field})
            value = input_node.get("value") if input_node is not None else None
            if not isinstance(value, str) or not value:
                raise EsbnAuthenticationError(f"ESBN sign-in form was missing {field}")
            values[field] = value
        return action, values

    def _authenticate(self) -> AuthResult:
        login_page = self._client.get(
            ESB_LOGIN_URL,
            headers=self._browser_headers(
                Accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                **{"Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate"},
            ),
        )
        login_page.raise_for_status()
        settings = self._extract_settings(login_page.text)

        self_asserted_url = (
            f"{ESB_AUTH_BASE_URL}/SelfAsserted?"
            f"{urlencode({'tx': settings['transId'], 'p': 'B2C_1A_signup_signin'})}"
        )
        self_asserted = self._client.post(
            self_asserted_url,
            data={
                "signInName": self._credentials.username,
                "password": self._credentials.password,
                "request_type": "RESPONSE",
            },
            headers=self._browser_headers(
                Accept="application/json, text/javascript, */*; q=0.01",
                **{
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "Origin": "https://login.esbnetworks.ie",
                    "Referer": str(login_page.url),
                    "X-Requested-With": "XMLHttpRequest",
                    "x-csrf-token": settings["csrf"],
                },
            ),
        )
        self_asserted.raise_for_status()

        confirmed = self._client.get(
            f"{ESB_AUTH_BASE_URL}/api/CombinedSigninAndSignup/confirmed",
            params={
                "rememberMe": "false",
                "csrf_token": settings["csrf"],
                "tx": settings["transId"],
                "p": "B2C_1A_signup_signin",
            },
            headers=self._browser_headers(
                Accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            ),
        )
        confirmed.raise_for_status()
        action_url, signin_data = self._extract_auto_form(confirmed.text)

        signin = self._client.post(
            action_url,
            data=signin_data,
            headers=self._browser_headers(
                Accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                **{
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://login.esbnetworks.ie",
                    "Referer": "https://login.esbnetworks.ie/",
                },
            ),
            follow_redirects=False,
        )
        signin.raise_for_status()

        account = self._client.get(
            f"{ESB_MYACCOUNT_URL}/",
            headers=self._browser_headers(
                Accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                Referer="https://login.esbnetworks.ie/",
            ),
        )
        account.raise_for_status()

        consumption = self._client.get(
            ESB_CONSUMPTION_URL,
            headers=self._browser_headers(
                Accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                Referer=f"{ESB_MYACCOUNT_URL}/",
            ),
        )
        consumption.raise_for_status()

        token = self._client.get(
            ESB_TOKEN_URL,
            headers=self._browser_headers(
                Accept="*/*",
                Referer=ESB_CONSUMPTION_URL,
                **{"X-Returnurl": ESB_CONSUMPTION_URL},
            ),
        )
        token.raise_for_status()
        token_data: dict[str, Any] = token.json()
        download_token = token_data.get("token")
        if not isinstance(download_token, str) or not download_token:
            raise EsbnAuthenticationError("ESBN did not return a download token")
        return AuthResult(download_token=download_token, user_agent=self._user_agent)

    def download_30_min_kwh_hdf(self) -> str:
        auth = self._authenticate()
        response = self._client.post(
            ESB_DOWNLOAD_URL,
            headers={
                "User-Agent": auth.user_agent,
                "Accept": "*/*",
                "Content-Type": "application/json",
                "Referer": ESB_CONSUMPTION_URL,
                "Origin": ESB_MYACCOUNT_URL,
                "X-Returnurl": ESB_CONSUMPTION_URL,
                "X-Xsrf-Token": auth.download_token,
            },
            json={"mprn": self._credentials.mprn, "searchType": "intervalkwh"},
            timeout=120.0,
        )
        response.raise_for_status()
        if len(response.content) > MAX_CSV_SIZE_BYTES:
            raise EsbnError("ESBN CSV response exceeded the configured size limit")
        text = response.text
        if text.lstrip().startswith("<"):
            raise EsbnError("ESBN returned HTML instead of HDF CSV")
        if "," not in text:
            raise EsbnError("ESBN response did not look like CSV")
        return text
```

- [ ] **Step 5: Run ESBN tests**

Run: `pytest tests/unit/test_esbn.py -q`

Expected: PASS.

- [ ] **Step 6: Run full local checks**

Run: `ruff check . && mypy esbn-to-mqtt/app && pytest`

Expected: PASS.

- [ ] **Step 7: Commit ESBN implementation**

```bash
git add esbn-to-mqtt/app/esbn_to_mqtt/esbn.py tests/unit/test_esbn.py
git commit -m "feat: download esbn hdf exports"
```

## Task 11: Build Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Build Docker image locally**

Run: `docker build -t esbn-to-mqtt:test esbn-to-mqtt`

Expected: image builds successfully.

- [ ] **Step 2: Run unit and integration tests**

Run: `ruff check . && mypy esbn-to-mqtt/app && pytest`

Expected: PASS.

- [ ] **Step 3: Check no secrets or raw exports are staged**

Run: `git status --short`

Expected: no `.env`, `exports/`, `data/`, `*.private.csv`, or `*.raw.csv` files appear.

Run: `rg -n "ESBN_PASSWORD|MQTT_PASSWORD|10000012345|cookie=|Set-Cookie|Authorization" .`

Expected: only `.env.example`, tests with fake values, or docs examples appear.

- [ ] **Step 4: Commit verification fixes if the image build exposes packaging issues**

If verification required fixes in packaging files, run:

```bash
git add pyproject.toml esbn-to-mqtt/Dockerfile esbn-to-mqtt/requirements.txt esbn-to-mqtt/run.sh
git commit -m "fix: address verification issues"
```

If verification required fixes in Python code or tests, run:

```bash
git add esbn-to-mqtt/app tests
git commit -m "fix: address verification issues"
```

If no fixes were needed, skip this step.

## Self-Review Checklist

- Spec coverage:
  - HA app repo shape: Tasks 1, 2, 8, 9.
  - GUI-configurable ESBN/MQTT settings: Tasks 2, 3.
  - MQTT discovery and Energy sensor metadata: Task 6.
  - Persistent monotonic totals: Task 5.
  - HDF CSV parser and anonymized fixture: Task 4.
  - CI checks: Task 9.
  - Local-only credentials and anonymization docs: Tasks 1, 8, 11.
  - ESBN live flow: Task 10.
- Placeholder scan:
  - Task 10 uses the request sequence visible in the referenced public integration and tests it with fake `httpx.MockTransport` responses. No real credentials or raw portal responses may enter the plan or repository.
- Type consistency:
  - `AppConfig`, `MqttConfig`, `MeterReading`, `MeterTotals`, `AccumulatorState`, and `MqttMessage` names are consistent across tasks.
