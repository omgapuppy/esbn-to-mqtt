# esbn-to-mqtt App Docs

## Configuration

Configure these settings in the app:

- `esbn_username`
- `esbn_password`
- `mprn`
- `mqtt_host` - default `core-mosquitto`
- `mqtt_port` - default `1883`
- `mqtt_username`
- `mqtt_password`
- `poll_interval_hours` - default `6`
- `mqtt_discovery_prefix` - default `homeassistant`
- `mqtt_topic_prefix` - default `esbn_to_mqtt`

## Energy Dashboard Setup

The app publishes MQTT discovery sensors that can be added to Home Assistant Energy:

- `ESBN Import Total` as grid consumption
- `ESBN Export Total` if export data exists
- `ESBN Last Update` as a diagnostic sensor

## Data Freshness

ESB Networks data is not real-time. Freshness depends on when the source data becomes available and on the configured polling interval.

## Troubleshooting

- ESBN auth or CAPTCHA failures: verify the ESBN username and password in a browser session first, then retry.
- Missing data: confirm the selected MPRN has data available and that the account can see the relevant meter history.
- MQTT credential failures: verify `mqtt_host`, `mqtt_port`, `mqtt_username`, and `mqtt_password`, and confirm the broker is reachable from the app environment.
- Stale data: check the polling interval and the app logs for failed fetch or publish attempts.

## Logging

Logs redact credentials and raw MPRNs. Do not paste sensitive values into issues or support threads.
