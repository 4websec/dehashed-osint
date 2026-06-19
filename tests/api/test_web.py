import base64
import os

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEHASHED_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint")
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    from src.core.config import get_settings
    get_settings.cache_clear()
    # Use as context manager so Starlette's TestClient keeps a single event
    # loop alive across all requests — required on Windows with asyncpg where
    # ProactorEventLoop connections cannot survive loop teardown between calls.
    with TestClient(create_app()) as c:
        yield c


def test_unauthorized_redirects_to_gate(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].endswith("/authorize")


def test_authorize_then_home_renders(client):
    client.post("/authorize", data={"ack": "yes"})
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Investigations" in resp.text
