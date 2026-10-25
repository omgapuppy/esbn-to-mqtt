# Changelog

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
