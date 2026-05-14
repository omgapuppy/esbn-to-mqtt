# Development

## Local setup

This repository expects a local virtual environment at the repo root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

Use a local `.env` file for developer-only values. Keep secrets out of git and never commit credentials, tokens, cookies, or other account data.

## Tests and lint

Run the standard checks from the repo root:

```bash
ruff check .
mypy esbn-to-mqtt/app
pytest
```

## Fixture anonymization

When adding or updating fixtures under `tests/fixtures/`, keep them anonymous and committed only in `_anonymized` form.

- Use the fake MPRN `10000000000`.
- Strip account IDs, names, addresses, cookies, and tokens.
- Shift timestamps if the original timing is sensitive.
- Scale readings if needed to preserve shape while removing real values.

Do not commit raw exports, screenshots, browser captures, or any fixture that still contains real customer data.
