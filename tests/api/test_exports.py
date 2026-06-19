"""Integration tests for the CSV / JSON / PDF export endpoints.

Uses respx to mock the DeHashed HTTP call so no real API key is needed.
The TestClient is used as a context manager to keep a single event loop
alive across all requests (required on Windows + asyncpg / ProactorEventLoop).
"""

import base64
import os

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.main import create_app

BASE = "https://api.dehashed.com/v2"


@pytest.fixture
def client(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DEHASHED_API_KEY", "k")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint_test"
    )
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("DEHASHED_BASE_URL", BASE)
    from src.core.config import get_settings

    get_settings.cache_clear()
    # Context manager keeps a single asyncio event loop alive on Windows where
    # ProactorEventLoop connections cannot survive loop teardown between calls.
    with TestClient(create_app()) as c:
        yield c


@respx.mock
def test_csv_export(client: TestClient) -> None:
    """CSV export returns text/csv with the expected email in the body."""
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 500,
                "total": 1,
                "entries": [{"email": "a@b.com", "database_name": "LeakA"}],
            },
        )
    )
    inv = client.post("/v1/investigations", json={"name": "Op"}).json()
    t = client.post(
        f"/v1/investigations/{inv['id']}/targets", json={"label": "jane"}
    ).json()
    client.post(
        f"/v1/targets/{t['id']}/searches",
        json={"field": "email", "value": "a@b.com"},
    )
    resp = client.get(f"/v1/targets/{t['id']}/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "a@b.com" in resp.text


@respx.mock
def test_json_export(client: TestClient) -> None:
    """JSON export returns application/json with the expected record."""
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 500,
                "total": 1,
                "entries": [{"email": "b@c.com", "database_name": "LeakB"}],
            },
        )
    )
    inv = client.post("/v1/investigations", json={"name": "Op2"}).json()
    t = client.post(
        f"/v1/investigations/{inv['id']}/targets", json={"label": "john"}
    ).json()
    client.post(
        f"/v1/targets/{t['id']}/searches",
        json={"field": "email", "value": "b@c.com"},
    )
    resp = client.get(f"/v1/targets/{t['id']}/export.json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    data = resp.json()
    assert isinstance(data, list)
    assert any(r.get("email") == "b@c.com" for r in data)


@respx.mock
def test_pdf_report(client: TestClient) -> None:
    """PDF report returns application/pdf with a valid PDF magic header."""
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 500,
                "total": 1,
                "entries": [{"email": "c@d.com", "database_name": "LeakC"}],
            },
        )
    )
    inv = client.post("/v1/investigations", json={"name": "Op3"}).json()
    t = client.post(
        f"/v1/investigations/{inv['id']}/targets", json={"label": "alice"}
    ).json()
    client.post(
        f"/v1/targets/{t['id']}/searches",
        json={"field": "email", "value": "c@d.com"},
    )
    resp = client.get(f"/v1/targets/{t['id']}/report.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    # ReportLab always begins the PDF with the %PDF magic bytes.
    assert resp.content[:4] == b"%PDF"


def test_pdf_report_404(client: TestClient) -> None:
    """PDF report returns 404 for a non-existent target."""
    resp = client.get("/v1/targets/99999/report.pdf")
    assert resp.status_code == 404
