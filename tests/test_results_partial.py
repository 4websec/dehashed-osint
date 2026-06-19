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

_TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "templates"


def _render_results(email: str) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),  # match Jinja2Templates default
    )
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
