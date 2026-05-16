# esbn-to-mqtt

`esbn-to-mqtt` is an unofficial Home Assistant app that turns ESB Networks smart meter HDF exports into MQTT sensors for Home Assistant.

It signs in to the ESB Networks portal, downloads the 30-minute kWh export, keeps a monotonic local accumulator for the Home Assistant Energy dashboard, and publishes extra dashboard/diagnostic sensors so you can see freshness, recent interval usage, daily/monthly totals, auth path, and CAPTCHA activity.

This is not a HACS integration and is not affiliated with, endorsed by, or connected to ESB Networks.

<p>
  <a href="https://www.buymeacoffee.com/omgapuppy" target="_blank">
    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="60" width="217">
  </a>
</p>

## What It Publishes

- Energy dashboard totals: `ESBN Import Total`, plus `ESBN Export Total` when export data exists.
- Recent visibility: latest 30-minute import/export interval.
- Period totals: today and current month import/export.
- Freshness: latest ESBN interval start and data lag.
- Diagnostics: last successful update, HDF rows parsed, new interval values processed, auth path, and CAPTCHA usage.

## How It Works

1. Reuse saved ESBN session cookies when the portal still accepts them.
2. Fall back to username/password login only when the session has expired.
3. Optionally solve ESBN reCAPTCHA challenges through 2Captcha when configured.
4. Download the 30-minute HDF export and parse import/export kWh readings.
5. Publish retained MQTT discovery and state messages for Home Assistant.

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

For app-specific setup, open the app **Documentation** tab in Home Assistant or see [`esbn-to-mqtt/DOCS.md`](esbn-to-mqtt/DOCS.md).

For local development, see [`docs/development.md`](docs/development.md).

## Status

This project is built for a practical Home Assistant setup using the default MQTT broker path first. ESBN portal flows can change, and automated polling may be interrupted by authentication, CAPTCHA, or portal-side changes.
