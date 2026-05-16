# esbn-to-mqtt

Publish ESB Networks smart meter readings to Home Assistant over MQTT.

This app signs in to ESB Networks, downloads the 30-minute kWh HDF export, keeps a monotonic local accumulator, and publishes retained MQTT discovery sensors for the Home Assistant Energy dashboard.

## What You Get

- `ESBN Import Total` for grid consumption
- `ESBN Export Total` when export data exists
- `ESBN Last Update` as a diagnostic sensor
- Recent interval, daily, monthly, lag, auth, CAPTCHA, and HDF parse diagnostics
- Configurable polling, defaulting to every 6 hours
- Optional 2Captcha solving when ESBN presents a reCAPTCHA challenge
- Redacted logs for credentials and MPRNs

## Setup

Open the **Documentation** tab for configuration details, Energy dashboard setup, data freshness notes, and troubleshooting.

The first-pass setup assumes the Home Assistant Mosquitto broker is already installed and available at `core-mosquitto`.

## Status

This is an unofficial app and is not affiliated with ESB Networks. The ESBN portal flow may change, and CAPTCHA or challenge pages can interrupt automated polling.
