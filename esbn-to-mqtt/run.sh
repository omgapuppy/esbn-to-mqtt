#!/usr/bin/env sh
set -eu

export PYTHONPATH=/app
exec python3 -m esbn_to_mqtt.main --options /data/options.json --data-dir /data
