# Changelog

## 0.5.0

- Add opt-in hourly grid import history in Home Assistant Recorder. Set
  `hourly_statistics_enabled: true` to backfill complete hours from ESBN at their actual times.
- The app gives each meter its own statistic and uses Recorder's existing history to preserve
  cumulative totals across reinstalls and ESBN corrections.
- After the first import, replace **ESBN Import Total** with **ESBN Hourly Grid Import** in the
  Energy dashboard to avoid double-counting. Export and tariff cost continue through MQTT.
  See [Opt-in hourly grid import](DOCS.md#opt-in-hourly-grid-import) for setup and rollback.

## 0.4.7

- Restore HDF downloads by using the new ESB Networks consumption endpoint after the previous endpoint began returning HTTP 405.

## 0.4.6

- Publish a preferred generic multi-architecture image for current Home Assistant releases.
- Update the Home Assistant base image to Alpine 3.24 and test Python 3.12 and 3.14.
- Mark update timestamps as timestamp sensors and keep release version metadata synchronized.
- Add regression coverage for the ESBN HDF download return header.

## 0.4.5

- Restore HDF downloads after ESB Networks began requiring the `x-ReturnUrl` request header.

## 0.4.4

- Interpret ESBN HDF timestamps in Irish local time so readings align correctly during IST.
- Preserve both repeated intervals during the autumn clock change and handle the spring transition.
- Migrate existing cached interval and tariff state automatically, retaining accumulated totals.

## 0.4.3

- Fix Home Assistant discovery metadata for monetary cost totals and latest interval kWh sensors.
- Add CODEOWNERS so protected branches can require owner review.

## 0.4.2

- Add HDF export stuck diagnostics when ESBN row counts fall while the latest interval does not advance.
- Log a warning after repeated stuck HDF export observations.

## 0.4.1

- Adjust accumulated import, export, and tariff cost totals when ESBN revises already-seen interval values.
- Log successful poll diagnostics including parsed rows, latest interval, data lag, and new values processed.

## 0.1.0

- Initial experimental Home Assistant app release.
