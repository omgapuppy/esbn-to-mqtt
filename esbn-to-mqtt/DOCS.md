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
- `captcha_solver` - default `disabled`; set to `2captcha` to solve ESBN reCAPTCHA challenges
- `two_captcha_api_key` - required only when `captcha_solver` is `2captcha`
- `two_captcha_timeout_seconds` - default `120`
- `log_level` - default `info`; accepted values `trace`, `debug`, `info`, `notice`, `warning`, `error`, `fatal`

## Energy Dashboard Setup

The app publishes MQTT discovery sensors that can be added to Home Assistant Energy:

- `ESBN Import Total` as grid consumption
- `ESBN Export Total` if export data exists
- `ESBN Last Update` as a diagnostic sensor

## Data Freshness

The app now fetches live ESBN data during each poll. Freshness depends on the source portal exposing updated readings and on the configured polling interval, so new consumption values can still lag behind the meter by a few hours.

The app stores ESBN session cookies in its Home Assistant app data directory and reuses them on later polls. This avoids a full username/password login on every poll when ESBN keeps the session valid.

## CAPTCHA Solving

ESBN can require an "I'm not a robot" check during sign-in. By default, the app detects this and backs off until the next poll.

If `captcha_solver` is set to `2captcha`, the app only calls 2Captcha after ESBN returns that reCAPTCHA challenge page. Normal session-cookie reuse and normal username/password sign-in do not call the solver. 2Captcha usage can incur charges, so leave this disabled unless ESBN is blocking automated sign-in for your account.

## Troubleshooting

- ESBN auth failures usually mean the username or password is wrong, or the session was rejected by ESBN before the portal reached the download step.
- CAPTCHA or challenge pages stop the login flow unless `captcha_solver` is configured. When the solver is disabled and ESBN asks for a browser challenge, the app backs off until the next configured poll instead of retrying every few minutes. Retry later, or sign in manually in a browser to confirm the account is usable.
- Missing data: confirm the selected MPRN has data available and that the account can see the relevant meter history.
- MQTT credential failures: verify `mqtt_host`, `mqtt_port`, `mqtt_username`, and `mqtt_password`, and confirm the broker is reachable from the app environment.
- Stale data: check the polling interval and the app logs for failed fetch or publish attempts.

## Logging

Logs redact credentials and raw MPRNs. Do not paste sensitive values, saved session cookies, or raw app data files into issues or support threads.
