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
- `tariff_enabled` - default `false`; enables import cost sensors
- `tariff_day_rate_eur_per_kwh` - VAT-inclusive day unit rate in currency/kWh
- `tariff_night_rate_eur_per_kwh` - VAT-inclusive night unit rate in currency/kWh
- `tariff_peak_rate_eur_per_kwh` - VAT-inclusive peak unit rate in currency/kWh
- `tariff_currency` - default `EUR`
- `log_level` - default `info`; accepted values `trace`, `debug`, `info`, `notice`, `warning`, `error`, `fatal`

## Energy Dashboard Setup

The app publishes MQTT discovery sensors that can be added to Home Assistant Energy:

- `ESBN Import Total` as grid consumption
- `ESBN Export Total` if export data exists
- `ESBN Last Update` as a diagnostic sensor

The app also publishes dashboard and diagnostic sensors:

- `ESBN Latest Interval Import` and `ESBN Latest Interval Export`
- `ESBN Today Import` and `ESBN Today Export`
- `ESBN Current Month Import` and `ESBN Current Month Export`
- `ESBN Data Lag`
- `ESBN Latest Interval Start`
- `ESBN New Values Processed`
- `ESBN HDF Rows Parsed`
- `ESBN CAPTCHA Used`
- `ESBN Auth Path`

If tariff costing is enabled, the app also publishes:

- `ESBN Import Cost Total`
- `ESBN Today Import Cost`
- `ESBN Current Month Import Cost`
- `ESBN Current Tariff`
- `ESBN Current Tariff Rate`

## Tariff Costing

Tariff rates are user-entered unit rates in currency/kWh. They should include whatever VAT or discount treatment you want reflected in Home Assistant. Standing charges, levies, PSO, and other bill items are intentionally out of scope.

The built-in smart tariff periods are:

- Night: 23:00-08:00 Europe/Dublin local time
- Peak: 17:00-19:00 Europe/Dublin local time
- Day: 08:00-17:00 and 19:00-23:00 Europe/Dublin local time

The app calculates cost from each 30-minute import interval and stores processed cost interval IDs in the app data directory so future polls do not double-charge the same HDF rows.

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
