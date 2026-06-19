import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.main import create_app

BASE = "https://api.dehashed.com/v2"


@pytest.fixture
def client(monkeypatch):
    import base64
    import os

    monkeypatch.setenv("DEHASHED_API_KEY", "k")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint"
    )
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("DEHASHED_BASE_URL", BASE)
    from src.core.config import get_settings

    get_settings.cache_clear()
    # Use as context manager so Starlette's TestClient keeps a single event
    # loop alive across all requests — required on Windows with asyncpg where
    # ProactorEventLoop connections cannot survive loop teardown between calls.
    with TestClient(create_app()) as c:
        yield c


@respx.mock
def test_rate_limit_upstream_yields_503(client):
    """DeHashed 429 after all retries must surface as 503 from the v1 route."""
    # Return 429 for every attempt so all retries are exhausted and the client
    # raises DehashedRateLimitError, which the route maps to 503.
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(429, json={"error": "rate limited"})
    )
    inv = client.post("/v1/investigations", json={"name": "RateOp"}).json()
    target = client.post(
        f"/v1/investigations/{inv['id']}/targets", json={"label": "victim"}
    ).json()
    run = client.post(
        f"/v1/targets/{target['id']}/searches",
        json={"field": "email", "value": "x@x.com"},
    )
    assert run.status_code == 503


@respx.mock
def test_full_investigation_search_flow(client):
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 500,
                "total": 1,
                "took": "2ms",
                "entries": [{"email": "a@b.com", "database_name": "LeakA"}],
            },
        )
    )
    inv = client.post("/v1/investigations", json={"name": "Op"}).json()
    target = client.post(
        f"/v1/investigations/{inv['id']}/targets", json={"label": "jane"}
    ).json()
    run = client.post(
        f"/v1/targets/{target['id']}/searches",
        json={"field": "email", "value": "a@b.com"},
    )
    assert run.status_code == 200
    assert run.json()["balance_after"] == 500
    profile = client.get(f"/v1/targets/{target['id']}/profile").json()
    assert profile["emails"] == ["a@b.com"]
    graph = client.get(f"/v1/targets/{target['id']}/graph").json()
    assert any(n["data"]["id"] == "email:a@b.com" for n in graph["nodes"])
