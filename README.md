# esbn-to-mqtt

`esbn-to-mqtt` is an unofficial Home Assistant app scaffold with an MQTT discovery pipeline for the Home Assistant Energy dashboard. Live ESBN download is still pending in development and will land in Task 10.

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
