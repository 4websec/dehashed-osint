"""Regression tests for the _results.html pivot-button hx-vals rendering.

The pivot button passes its values to HTMX via the ``hx-vals`` attribute, which
HTMX parses as JSON. The attribute is double-quoted, so the JSON's own double
quotes (and any quotes/angle brackets in leaked data) must be HTML-entity
encoded — otherwise the attribute breaks early and HTMX raises a JSON
SyntaxError, sends no form fields, and the search route returns 422.
"""

import html as html_lib
import json
import re
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.api.web.pages import reuse_color as _reuse_color
from src.services.correlation_service import identify_hash_type

_TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "templates"


def _render_results(email: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),  # match Jinja2Templates default
    )
    env.filters["hash_type"] = identify_hash_type  # match pages.py registration
    rec = SimpleNamespace(
        email=email,
        username="u",
        password=None,
        hashed_password="$2a$08$abcdef",
        database_name="LeakA",
    )
    return env.get_template("_results.html").render(
        records=[rec], target_id=1, profile=None
    )


def test_pivot_hx_vals_is_valid_json_for_plain_email():
    rendered = _render_results("adriennebalkum@gmail.com")
    match = re.search(r'hx-vals="([^"]*)"', rendered)
    assert match, "hx-vals attribute not found"
    data = json.loads(html_lib.unescape(match.group(1)))
    assert data == {"field": "email", "value": "adriennebalkum@gmail.com"}


def test_pivot_hx_vals_survives_hostile_characters():
    # Quotes/angle brackets in leaked breach data previously broke the attribute
    # (JSON SyntaxError -> 422) and were an XSS breakout vector.
    email = "o'bri<en\">@x.com"
    rendered = _render_results(email)
    match = re.search(r'hx-vals="([^"]*)"', rendered)
    assert match, "hx-vals attribute not found"
    raw_attr = match.group(1)
    # Browser decodes HTML entities before HTMX reads the attribute -> valid JSON.
    data = json.loads(html_lib.unescape(raw_attr))
    assert data == {"field": "email", "value": email}
    # No raw double-quote or angle bracket may survive in the attribute itself.
    assert '"' not in raw_attr
    assert "<" not in raw_attr


def _render_with_profile(records, profile):
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["hash_type"] = identify_hash_type
    env.filters["reuse_color"] = _reuse_color
    return env.get_template("_results.html").render(
        records=records, target_id=1, profile=profile
    )


def test_reused_password_row_is_marked():
    rec_a = SimpleNamespace(
        email="a@b.com",
        username="u",
        password="reuse",
        hashed_password=None,
        database_name="LeakA",
    )
    rec_b = SimpleNamespace(
        email="a@b.com",
        username="u",
        password="reuse",
        hashed_password=None,
        database_name="LeakB",
    )
    profile = SimpleNamespace(
        reuse_counts={"reuse": 2},
        breach_sources={"LeakA": 1, "LeakB": 1},
        reused_passwords=["reuse"],
        hash_types={},
    )
    html = _render_with_profile([rec_a, rec_b], profile)
    assert "reuse-stamp" in html
    assert "×2" in html
    assert html.count('class="reused"') == 2


def test_non_reused_password_row_is_not_marked():
    rec = SimpleNamespace(
        email="a@b.com",
        username="u",
        password="solo",
        hashed_password=None,
        database_name="LeakA",
    )
    profile = SimpleNamespace(
        reuse_counts={},
        breach_sources={"LeakA": 1},
        reused_passwords=[],
        hash_types={},
    )
    html = _render_with_profile([rec], profile)
    assert "reuse-stamp" not in html


def test_revealable_cell_has_copy_control():
    rec = SimpleNamespace(
        email="a@b.com",
        username="u",
        password="pw",
        hashed_password=None,
        database_name="LeakA",
    )
    profile = SimpleNamespace(
        reuse_counts={},
        breach_sources={"LeakA": 1},
        reused_passwords=[],
        hash_types={},
    )
    html = _render_with_profile([rec], profile)
    assert 'class="copy"' in html


def test_result_cells_have_data_labels():
    rec = SimpleNamespace(
        email="a@b.com",
        username="u",
        password=None,
        hashed_password=None,
        database_name="LeakA",
    )
    profile = SimpleNamespace(
        reuse_counts={},
        breach_sources={"LeakA": 1},
        reused_passwords=[],
        hash_types={},
    )
    html = _render_with_profile([rec], profile)
    assert 'data-label="Email"' in html
    assert 'data-label="Source"' in html
