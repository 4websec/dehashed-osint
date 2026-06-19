"""App-boot smoke test.

Verifies that create_app() produces a working FastAPI application and that
GET /healthz returns {"status": "ok"} without requiring a live Postgres
connection (create_async_engine is lazy — the engine is constructed but no
socket is opened until the first query).
"""

import base64
import os

import pytest
from fastapi.testclient import TestClient


def _clear_settings_cache() -> None:
    """Bust the lru_cache on get_settings so each test sees fresh env vars."""
    from src.core.config import get_settings

    get_settings.cache_clear()


def test_healthz(monkeypatch: pytest.MonkeyPatch) -> None:
    # Provide the minimum env vars that Settings requires.
    monkeypatch.setenv("DEHASHED_API_KEY", "test-boot-key")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://osint:osint@localhost:5432/osint",
    )
    monkeypatch.setenv(
        "ENCRYPTION_KEY",
        base64.b64encode(os.urandom(32)).decode(),
    )

    # Clear the lru_cache so create_app() reads the monkeypatched env vars
    # instead of a cached Settings object from a previous test run.
    _clear_settings_cache()

    from src.main import create_app

    client = TestClient(create_app())
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
