import base64
import os

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEHASHED_API_KEY", "k")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint_test"
    )
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
    assert "Case Files" in resp.text  # home renders the case-file dossier shell


def test_create_investigation_xss_name_is_escaped(client):
    """Stored XSS regression: HTML in investigation name must be escaped."""
    client.post("/authorize", data={"ack": "yes"})
    xss_payload = "<script>alert(1)</script>"
    resp = client.post("/ui/investigations", data={"name": xss_payload})
    assert resp.status_code == 200
    # Raw script tag must NOT appear — it must be HTML-entity-encoded.
    assert "<script>" not in resp.text
    assert "&lt;script&gt;" in resp.text


def test_investigation_to_target_navigation_flow(client):
    """Regression: investigations link to /ui/investigations/{id}; that page
    lets you create a target that links to a valid /ui/targets/{target_id}
    (not /ui/targets/{investigation_id}), and the target page renders with a
    non-empty search-form action (the //search 404 bug)."""
    client.post("/authorize", data={"ack": "yes"})

    # Create an investigation; the returned fragment must link to its detail
    # page, NOT straight to a target page.
    frag = client.post("/ui/investigations", data={"name": "Op Nav"})
    assert frag.status_code == 200
    assert "/ui/investigations/1" in frag.text
    assert "/ui/targets/" not in frag.text

    # The investigation detail page renders an add-target form.
    page = client.get("/ui/investigations/1")
    assert page.status_code == 200
    assert "/ui/investigations/1/targets" in page.text

    # Create a target under the investigation; fragment links to the TARGET.
    tfrag = client.post("/ui/investigations/1/targets", data={"label": "jane"})
    assert tfrag.status_code == 200
    assert "/ui/targets/1" in tfrag.text

    # The target page renders a search form whose action has a real id — no
    # empty `/ui/targets//search`.
    tpage = client.get("/ui/targets/1")
    assert tpage.status_code == 200
    assert "/ui/targets/1/search" in tpage.text
    assert "/ui/targets//search" not in tpage.text


def test_missing_target_returns_404(client):
    """A target id that does not exist must 404, not render a broken form."""
    client.post("/authorize", data={"ack": "yes"})
    resp = client.get("/ui/targets/99999")
    assert resp.status_code == 404


def test_missing_investigation_returns_404(client):
    client.post("/authorize", data={"ack": "yes"})
    resp = client.get("/ui/investigations/99999")
    assert resp.status_code == 404
