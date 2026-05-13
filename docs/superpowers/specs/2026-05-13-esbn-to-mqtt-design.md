# esbn-to-mqtt Design

## Goal

Build `esbn-to-mqtt`, a public Home Assistant app repository containing one app that logs into ESB Networks, retrieves smart meter HDF CSV data, and publishes Home Assistant-compatible MQTT discovery and state topics for the Energy dashboard.

This is a selfish first pass for a Home Assistant OS installation that already has the default MQTT broker enabled and in use. Other output paths are explicitly out of scope for the first version.

## Non-Goals

- Do not build a HACS integration or custom Home Assistant component.
- Do not write directly to Home Assistant Core entities through the Home Assistant REST API.
- Do not support non-MQTT output paths in the first version.
- Do not commit ESBN credentials, real MPRNs, raw private exports, or logs containing secrets.
- Do not run a full Home Assistant instance in CI yet.

## Repository Shape

The repository is a Home Assistant app repository, not a single Python package repository.

Planned top-level files:

- `repository.yaml` describes the app repository for Home Assistant.
- `README.md` explains installation, scope, and links to app and development docs.
- `docs/development.md` explains local setup, `.env`, fixture anonymization, and test commands.
- `.env.example` contains stub values only.
- `.gitignore` excludes `.env`, local caches, build output, Python artifacts, and captured private exports.
- `.github/workflows/ci.yml` runs linting, unit tests, and integration tests on pull requests.
- `esbn-to-mqtt/` contains the Home Assistant app.

Planned app files:

- `esbn-to-mqtt/config.yaml` defines Supervisor GUI options.
- `esbn-to-mqtt/DOCS.md` contains app-store-facing installation and configuration docs.
- `esbn-to-mqtt/README.md` gives a short app summary.
- `esbn-to-mqtt/CHANGELOG.md` starts the app changelog.
- `esbn-to-mqtt/Dockerfile` builds the app image from a Home Assistant-compatible base image.
- `esbn-to-mqtt/run.sh` starts the Python worker.
- `esbn-to-mqtt/app/` contains the Python worker code.

The Home Assistant app slug in `config.yaml` should be `esbn_to_mqtt`.

## Home Assistant App Configuration

The app exposes settings through `config.yaml` so they are configurable in the Home Assistant GUI.

Required options:

- `esbn_username`: ESB Networks account email.
- `esbn_password`: ESB Networks account password, typed as `password` in the schema.
- `mprn`: 11-digit meter point reference number.
- `mqtt_host`: MQTT broker host, default `core-mosquitto` for the common Home Assistant Mosquitto app path.
- `mqtt_port`: MQTT broker port, default `1883`.
- `mqtt_username`: MQTT username.
- `mqtt_password`: MQTT password, typed as `password`.

Optional options:

- `poll_interval_hours`: integer, default `6`, minimum `1`.
- `mqtt_discovery_prefix`: default `homeassistant`.
- `mqtt_topic_prefix`: default `esbn_to_mqtt`.
- `log_level`: enum with normal Home Assistant add-on levels, default `info`.

The app validates config on startup:

- MPRN must be exactly 11 digits.
- Poll interval must be positive.
- MQTT connection settings must be present.
- Secrets must never be logged.

## ESBN Data Source

ESB Networks documents smart meter data as HDF CSV downloads. Available downloads include:

- 30-minute readings in kW.
- 30-minute readings in kWh.
- Daily snapshot of day/night/peak usage in kWh.
- Daily snapshot of total usage and export data where applicable.

The first version should prefer the 30-minute kWh HDF CSV because Home Assistant Energy statistics expect energy in kWh, while the kW export describes average power over the interval and would require conversion. The parser should expose a small format-specific interface so additional ESBN export formats can be added later without changing MQTT publishing code.

The implementation should preserve raw fetched files only in `/data` for local cache/debugging and must not include real private exports in git. Any committed fixture must be anonymized first.

## Data Model

Internal parsed records represent half-hourly meter readings:

- `mprn`: sanitized or omitted in logs and fixtures.
- `timestamp`: timezone-aware interval start.
- `import_kwh`: imported energy for the interval.
- `export_kwh`: optional exported energy for the interval.
- `quality`: optional source quality marker if present in the CSV.

The worker derives cumulative totals from the interval data:

- Total import energy in kWh across the available series.
- Optional total export energy in kWh across the available series.
- Last successful ESBN fetch timestamp.
- Last interval timestamp.

If the ESBN HDF provides a cumulative register value in a selected format, that cumulative value should be preferred. If the selected HDF contains interval readings only, the app must maintain a persistent accumulator in `/data/state.json`:

- Track processed interval identifiers by timestamp and channel.
- Add only newly observed interval kWh values to the stored total.
- Keep publishing the stored cumulative total even if ESBN later returns a shorter rolling export.
- Rebuild the accumulator only when no prior `/data/state.json` exists.

This prevents the Home Assistant `total_increasing` energy sensor from dropping when ESBN's downloadable history window changes.

## MQTT Contract

The app publishes retained Home Assistant MQTT discovery config and retained state payloads.

Default topics:

- Availability: `esbn_to_mqtt/<safe_mprn>/availability`
- State: `esbn_to_mqtt/<safe_mprn>/state`
- Import discovery: `homeassistant/sensor/esbn_to_mqtt_<safe_mprn>_import_total/config`
- Export discovery, when export data exists: `homeassistant/sensor/esbn_to_mqtt_<safe_mprn>_export_total/config`
- Last update discovery: `homeassistant/sensor/esbn_to_mqtt_<safe_mprn>_last_update/config`

The main Energy dashboard entity is an import energy sensor:

- `device_class`: `energy`
- `state_class`: `total_increasing`
- `unit_of_measurement`: `kWh`
- `suggested_display_precision`: `3`
- `value_template`: extracts `import_total_kwh`
- `unique_id`: stable value derived from the app name, hashed MPRN, and sensor role.
- `availability_topic`: the app availability topic.

Optional export sensor uses the same energy metadata and extracts `export_total_kwh`.

Device metadata groups entities under one device:

- Manufacturer: `ESB Networks`
- Model: `Smart Meter`
- Name: `ESBN Smart Meter`
- Identifiers: app-owned identifier derived from a hashed MPRN, not the raw MPRN.

The state payload should include:

```json
{
  "import_total_kwh": 1234.567,
  "export_total_kwh": 12.345,
  "last_interval_start": "2026-05-13T00:00:00+01:00",
  "last_successful_fetch": "2026-05-13T08:15:00+01:00",
  "source": "esb_networks_hdf_30_min_kwh"
}
```

Fields with unavailable values may be omitted, except the primary import value must be present before publishing an online availability status.

## Polling and Runtime Behavior

The app runs continuously:

1. Load and validate Supervisor options from `/data/options.json`.
2. Connect to MQTT.
3. Publish discovery configs.
4. Poll ESBN immediately on startup.
5. Parse the selected HDF CSV.
6. Publish state and `online` availability if successful.
7. Sleep for `poll_interval_hours`.
8. On transient failure, retry with bounded backoff without hammering ESBN.
9. Publish `offline` availability only when no usable cached state exists or the app cannot continue.

Default polling is every 6 hours. ESBN data is not real-time, but 6 hours is useful for timely overnight updates while staying conservative.

## Error Handling

Errors are classified:

- Configuration errors: fail fast with a clear log message.
- MQTT connection errors: retry with backoff.
- ESBN authentication errors: log a redacted message and retry on the next polling cycle.
- CAPTCHA or anti-automation challenge: log a redacted actionable message and avoid rapid retries.
- CSV format errors: keep the last known good MQTT state and mark diagnostics in logs.
- Empty/no-new-data responses: keep the last state and publish an updated last fetch only if the source response was valid.

No error path may log passwords, cookies, bearer tokens, full raw HTML auth responses, or raw MPRNs.

## Credential and Data Safety

Local development uses `.env`, which is gitignored. `.env.example` contains only stubs.

Real ESBN credentials and MPRNs may be used only locally for testing. Captured exports must be anonymized before committing:

- Replace MPRN with a fixed fake 11-digit value.
- Shift timestamps if needed.
- Scale or otherwise perturb readings while keeping realistic shape.
- Strip names, addresses, account IDs, cookies, auth tokens, and hidden metadata.
- Keep enough rows to exercise parsing and aggregation.

The app should mask MPRNs in logs, showing at most the last 3 digits when needed.

## Testing Strategy

Unit tests:

- Config validation.
- MPRN masking and hashing.
- HDF CSV parser for expected 30-minute kWh import rows.
- Optional export parsing.
- Aggregation into total import/export kWh.
- MQTT discovery payload structure.
- State payload generation.
- Secret redaction behavior.

Integration tests:

- Load anonymized fixture CSV.
- Run parser and aggregator end to end.
- Publish through a mocked or local MQTT client interface.
- Assert discovery topics and retained state payloads are correct.

CI runs on pull requests and pushes to non-protected branches:

- Python lint/format check.
- Unit tests.
- Integration tests with anonymized fixtures.
- YAML validation for Home Assistant app metadata.

Full HA Supervisor installation tests are a future improvement.

## Documentation

`README.md` should stay concise:

- What the app does.
- It is unofficial and not affiliated with ESB Networks.
- It requires Home Assistant OS/Supervisor apps and an MQTT broker.
- How to add the GitHub app repository to Home Assistant.
- Link to app docs and development docs.

`esbn-to-mqtt/DOCS.md` should include:

- Installation steps.
- Required ESBN and MQTT configuration.
- Energy dashboard setup.
- Poll interval guidance.
- Troubleshooting for ESBN auth, CAPTCHA, missing data, MQTT connectivity, and stale data.

`docs/development.md` should include:

- Python/local test setup.
- `.env` usage.
- How to capture and anonymize ESBN exports.
- CI commands.
- Secret-handling rules.

## GitHub Repository Controls

The repo is public at `https://github.com/omgapuppy/esbn-to-mqtt`.

`main` is protected with:

- Required pull request review for non-admin changes.
- Dismiss stale reviews.
- Required conversation resolution.
- Required linear history.
- Force pushes disabled.
- Deletions disabled.

GitHub personal repositories do not support explicit per-user push restrictions through branch protection. Owner/admin bypass remains the practical route for the account owner while contributors must work through pull requests.

## Open Implementation Decisions

- Exact ESBN auth implementation will be derived during implementation from the working portal flow and the referenced existing integration, but secrets and raw auth responses must remain out of git.
- Exact HDF CSV column names will be locked down after obtaining a current export from the user's account or from a committed anonymized fixture.
- The container base image should follow current Home Assistant app documentation, avoiding reliance on deprecated default `BUILD_FROM` behavior.
