# tests/conftest.py
import pytest


@pytest.fixture(autouse=True)
def no_supervisor_token(monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep every test hermetic: nothing may reach a real Home Assistant websocket.
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
