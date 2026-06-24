"""Template-render tests for target.html (no DB; direct Jinja env)."""

import re
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.services.correlation_service import identify_hash_type

_TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "templates"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["hash_type"] = identify_hash_type
    return env


def _render_target(records=None) -> str:
    target = SimpleNamespace(id=1, label="jane@x.com", investigation_id=2)
    return (
        _env()
        .get_template("target.html")
        .render(
            target=target,
            fields=["address", "email", "username"],
            records=records or [],
            profile=None,
            balance=None,
            target_id=1,
            request=SimpleNamespace(),
        )
    )


def test_search_button_has_pending_state():
    html = _render_target()
    assert 'hx-disabled-elt="this"' in html
    assert 'class="spin"' in html


def test_base_declares_favicon():
    html = _render_target()
    assert 'rel="icon"' in html
    assert "/static/favicon.svg" in html


def test_export_toolbar_hidden_when_no_records():
    html = _render_target(records=[])
    assert "PDF dossier" not in html


def test_export_toolbar_shown_with_records():
    rec = SimpleNamespace(
        email="a@b.com",
        username=None,
        password=None,
        hashed_password=None,
        database_name="LeakA",
    )
    html = _render_target(records=[rec])
    assert "PDF dossier" in html


def test_email_selector_is_default_selected():
    html = _render_target()
    m = re.search(r'<option value="email"[^>]*>', html)
    assert m and "selected" in m.group(0)
