# Changelog

## 0.4.2

- Add HDF export stuck diagnostics when ESBN row counts fall while the latest interval does not advance.
- Log a warning after repeated stuck HDF export observations.

## 0.4.1

- Adjust accumulated import, export, and tariff cost totals when ESBN revises already-seen interval values.
- Log successful poll diagnostics including parsed rows, latest interval, data lag, and new values processed.

## 0.1.0

- Initial experimental Home Assistant app release.
