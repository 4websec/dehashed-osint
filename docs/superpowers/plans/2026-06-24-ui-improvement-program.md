# UI Improvement Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the DeHashed web UI across three tracks — search feedback & polish, password-reuse surfacing, and mobile responsiveness — without touching the API contract or auth model.

**Architecture:** Server-rendered HTMX/Jinja UI. Track 1 is template + CSS only. Track 2 adds one field to `TargetProfile`, populates it in `CorrelationService`, and renders per-row reuse markers + a reveal-gated copy control. Track 3 is CSS + `data-label` attributes for a mobile card layout. Each track is a discrete commit and ships independently.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, HTMX (bundled, supports `hx-indicator`/`hx-disabled-elt`), Pydantic v2, pytest. Frontend is vanilla CSS/JS ("Redacted Dossier" design system in `src/static/app.css`).

## Global Constraints

- Quality gate per track: `black . && ruff check . && mypy && pytest` — all must pass. `alembic/` is excluded from ruff/mypy.
- User input is leaked breach data — always escape into markup (templates autoescape; `pages.py` uses `markupsafe.escape` for f-string fragments). Never introduce a raw-interpolation XSS vector.
- Reuse semantics (unchanged): a plaintext password under **>1 distinct breach source**.
- Template/partial tests render via a direct Jinja `Environment` (no DB) — follow the pattern in `tests/test_results_partial.py`. Tests touching `CorrelationService.build_profile` use the `db_session` fixture (**requires Postgres** — `osint_test` DB).
- ⚠ **Environment prerequisite:** `pytest` needs Postgres running. At plan time Docker is down and Poetry's interpreter path is broken; restore the toolchain (start Docker/Postgres, repair the Poetry Python) before running the gate. Pure-Jinja and filter unit tests run without Postgres.
- The reuse marker must be visible while the password cell is still redacted; it must not reveal the plaintext.

---

## Track 1 — Search feedback & polish (P1)

### Task 1: Search pending state

**Files:**
- Modify: `src/templates/target.html` (search form button, ~lines 13-26)
- Modify: `src/static/app.css` (append spinner + request-state rules)
- Test: `tests/test_target_page.py` (new)

**Interfaces:**
- Consumes: existing `target.html` context (`target`, `fields`, `records`, `profile`, `balance`, `target_id`).
- Produces: nothing for later tasks (presentational).

- [ ] **Step 1: Write the failing test**

Create `tests/test_target_page.py`:

```python
"""Template-render tests for target.html (no DB; direct Jinja env)."""
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
    return _env().get_template("target.html").render(
        target=target,
        fields=["address", "email", "username"],
        records=records or [],
        profile=None,
        balance=None,
        target_id=1,
        request=SimpleNamespace(),
    )


def test_search_button_has_pending_state():
    html = _render_target()
    assert 'hx-disabled-elt="this"' in html
    assert 'class="spin"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_target_page.py::test_search_button_has_pending_state -v`
Expected: FAIL (`assert 'hx-disabled-elt="this"' in html` — attribute absent).

- [ ] **Step 3: Implement the markup**

In `src/templates/target.html`, replace the submit button:

```html
    <button class="btn" type="submit">Run search</button>
```

with (the label carries its busy text in `data-busy` so CSS can swap it):

```html
    <button class="btn" type="submit" hx-disabled-elt="this">
      <span class="spin" aria-hidden="true"></span>
      <span class="btn-label" data-busy="Searching…">Run search</span>
    </button>
```

- [ ] **Step 4: Add the CSS**

Append to `src/static/app.css`:

```css
/* --- search pending state ----------------------------------------------- */
.btn .spin { display: none; }
.btn[disabled] { opacity: 0.7; cursor: progress; }
.btn.htmx-request .spin {
  display: inline-block;
  width: 0.7em; height: 0.7em;
  margin-right: 0.45em;
  border: 2px solid rgba(17,21,28,0.35);
  border-top-color: var(--carbon);
  border-radius: 50%;
  vertical-align: -1px;
  animation: btnspin 0.6s linear infinite;
}
/* swap the label "Run search" -> "Searching…" while the request is in flight */
.btn.htmx-request .btn-label { font-size: 0; }
.btn.htmx-request .btn-label::after {
  content: attr(data-busy);
  font-size: 0.82rem;  /* restore .btn font-size */
}
@keyframes btnspin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .btn.htmx-request .spin { animation: none; } }
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_target_page.py::test_search_button_has_pending_state -v`
Expected: PASS.

- [ ] **Step 6: Verify visually (manual)**

Render `target.html` with mock data and confirm in a browser (render-harness from design, or live app if Postgres is up) that clicking Run search disables the button and shows the spinner + "Searching…". Hard to assert in CI; visual check only.

- [ ] **Step 7: Commit**

```bash
git add src/templates/target.html src/static/app.css tests/test_target_page.py
git commit -m "feat(ui): search pending state (spinner + disabled button)"
```

---

### Task 2: Favicon

**Files:**
- Create: `src/static/favicon.svg`
- Modify: `src/templates/base.html` (add `<link rel="icon">`)
- Test: `tests/test_target_page.py` (add a case; base is included via target.html)

**Interfaces:** none consumed/produced.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_target_page.py`:

```python
def test_base_declares_favicon():
    html = _render_target()
    assert 'rel="icon"' in html
    assert "/static/favicon.svg" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_target_page.py::test_base_declares_favicon -v`
Expected: FAIL (no icon link).

- [ ] **Step 3: Create the favicon**

Create `src/static/favicon.svg` (the amber skewed-bar brand mark on carbon):

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="4" fill="#11151c"/>
  <rect x="11" y="6" width="7" height="20" rx="1" fill="#e0a33e" transform="skewX(-12)"/>
</svg>
```

- [ ] **Step 4: Add the link**

In `src/templates/base.html`, after the `<meta name="viewport"...>` line, add:

```html
  <link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_target_page.py::test_base_declares_favicon -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/static/favicon.svg src/templates/base.html tests/test_target_page.py
git commit -m "feat(ui): add favicon (kills /favicon.ico 404)"
```

---

### Task 3: Empty-target export chrome + selector default

**Files:**
- Modify: `src/templates/target.html` (wrap toolbar in `{% if records %}`; mark `email` selected)
- Test: `tests/test_target_page.py` (add cases)

**Interfaces:** none consumed/produced.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_target_page.py`:

```python
def test_export_toolbar_hidden_when_no_records():
    html = _render_target(records=[])
    assert "PDF dossier" not in html


def test_export_toolbar_shown_with_records():
    rec = SimpleNamespace(email="a@b.com", username=None, password=None,
                          hashed_password=None, database_name="LeakA")
    html = _render_target(records=[rec])
    assert "PDF dossier" in html


def test_email_selector_is_default_selected():
    html = _render_target()
    # the <option value="email"> must carry the selected attribute
    import re
    m = re.search(r'<option value="email"[^>]*>', html)
    assert m and "selected" in m.group(0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_target_page.py -k "toolbar or selector" -v`
Expected: `test_export_toolbar_hidden_when_no_records` FAILS (toolbar always rendered); `test_email_selector_is_default_selected` FAILS (no selected attr).

- [ ] **Step 3: Wrap the toolbar**

In `src/templates/target.html`, wrap the `<div class="toolbar">...</div>` block:

```html
  {% if records %}
  <div class="toolbar">
    ... existing toolbar contents unchanged ...
  </div>
  {% endif %}
```

(Leave the `<details class="manual">` field manual unconditional.)

- [ ] **Step 4: Default the selector to email**

In `src/templates/target.html`, change the option loop:

```html
        {% for f in fields %}<option value="{{ f }}">{{ f }}</option>{% endfor %}
```

to:

```html
        {% for f in fields %}<option value="{{ f }}"{% if f == "email" %} selected{% endif %}>{{ f }}</option>{% endfor %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_target_page.py -k "toolbar or selector" -v`
Expected: PASS (all three).

- [ ] **Step 6: Commit**

```bash
git add src/templates/target.html tests/test_target_page.py
git commit -m "feat(ui): hide export toolbar on empty targets; default selector to email"
```

---

## Track 2 — Surface password reuse (P2)

### Task 4: `reuse_counts` on TargetProfile

**Files:**
- Modify: `src/schemas/domain.py` (add field to `TargetProfile`)
- Modify: `src/services/correlation_service.py` (populate it)
- Test: `tests/services/test_correlation_service.py` (extend)

**Interfaces:**
- Produces: `TargetProfile.reuse_counts: dict[str, int]` — password → distinct breach-source count, only for passwords seen under >1 source. Consumed by Tasks 5 & 6.

- [ ] **Step 1: Write the failing test**

Add to `tests/services/test_correlation_service.py` (inside `test_build_profile_dedups_and_maps`, after the existing asserts):

```python
    assert profile.reuse_counts == {"reuse": 2}  # 2 distinct breaches; "other" (1 source) excluded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_correlation_service.py::test_build_profile_dedups_and_maps -v`
Expected: FAIL (`AttributeError: ... no attribute 'reuse_counts'` or `{} != {"reuse": 2}`). Requires Postgres.

- [ ] **Step 3: Add the field**

In `src/schemas/domain.py`, add to `TargetProfile` (after `reused_passwords`):

```python
    reuse_counts: dict[str, int] = Field(default_factory=dict)
```

- [ ] **Step 4: Populate it**

In `src/services/correlation_service.py` `build_profile`, after the `reused = [...]` line, add:

```python
        reuse_counts = {pw: len(srcs) for pw, srcs in pw_breaches.items() if len(srcs) > 1}
```

and add `reuse_counts=reuse_counts,` to the `TargetProfile(...)` constructor call.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/services/test_correlation_service.py::test_build_profile_dedups_and_maps -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/schemas/domain.py src/services/correlation_service.py tests/services/test_correlation_service.py
git commit -m "feat: add reuse_counts (password -> breach count) to TargetProfile"
```

---

### Task 5: `reuse_color` Jinja filter

**Files:**
- Modify: `src/api/web/pages.py` (define + register filter alongside `hash_type`)
- Test: `tests/test_reuse_color.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `reuse_color(password: str) -> str` — a deterministic CSS color string. Registered as Jinja filter `reuse_color`. Consumed by Task 6's template.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reuse_color.py`:

```python
from src.api.web.pages import reuse_color


def test_reuse_color_is_deterministic():
    assert reuse_color("hunter2") == reuse_color("hunter2")


def test_reuse_color_differs_for_different_inputs():
    # Not a hard guarantee across all inputs, but these two must differ.
    assert reuse_color("hunter2") != reuse_color("Summer2019!")


def test_reuse_color_returns_css_color():
    val = reuse_color("hunter2")
    assert val.startswith("hsl(")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_reuse_color.py -v`
Expected: FAIL (`ImportError: cannot import name 'reuse_color'`).

- [ ] **Step 3: Implement + register the filter**

In `src/api/web/pages.py`, after the `identify_hash_type` import usage / filter registration block (near line 33), add the function near module top (after imports) and register it:

```python
def reuse_color(password: str) -> str:
    """Deterministic on-brand hue for a reused password's group chip.

    A stable hash of the password maps to a hue; saturation/lightness are fixed
    so chips read as muted accents, not rainbow. Used only to disambiguate when
    multiple distinct reused passwords are present in one target.
    """
    h = 0
    for ch in password:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    hue = h % 360
    return f"hsl({hue}, 55%, 55%)"
```

And register beside the existing filter:

```python
_templates.env.filters["reuse_color"] = reuse_color
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_reuse_color.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/api/web/pages.py tests/test_reuse_color.py
git commit -m "feat(ui): deterministic reuse_color jinja filter for reuse chips"
```

---

### Task 6: Reuse row markers in `_results.html`

**Files:**
- Modify: `src/templates/_results.html` (row class, chip, stamp, summary)
- Modify: `src/static/app.css` (`.reuse-stamp`, `.reuse-chip`, `tr.reused td`)
- Test: `tests/test_results_partial.py` (extend)

**Interfaces:**
- Consumes: `profile.reuse_counts` (Task 4), `reuse_color` filter (Task 5).
- Produces: presentational.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_results_partial.py` (the existing `_render_results` passes `profile=None`; add a profile-aware renderer):

```python
from src.api.web.pages import reuse_color as _reuse_color


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
    rec_a = SimpleNamespace(email="a@b.com", username="u", password="reuse",
                            hashed_password=None, database_name="LeakA")
    rec_b = SimpleNamespace(email="a@b.com", username="u", password="reuse",
                            hashed_password=None, database_name="LeakB")
    profile = SimpleNamespace(reuse_counts={"reuse": 2}, breach_sources={"LeakA": 1, "LeakB": 1},
                              reused_passwords=["reuse"], hash_types={})
    html = _render_with_profile([rec_a, rec_b], profile)
    assert "reuse-stamp" in html
    assert "×2" in html
    assert html.count('class="reused"') == 2 or html.count("reused") >= 2


def test_non_reused_password_row_is_not_marked():
    rec = SimpleNamespace(email="a@b.com", username="u", password="solo",
                          hashed_password=None, database_name="LeakA")
    profile = SimpleNamespace(reuse_counts={}, breach_sources={"LeakA": 1},
                              reused_passwords=[], hash_types={})
    html = _render_with_profile([rec], profile)
    assert "reuse-stamp" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_results_partial.py -k reused -v`
Expected: FAIL (`reuse-stamp` not present).

- [ ] **Step 3: Update the password cell + row**

In `src/templates/_results.html`, change the row opening and the password `<td>`. The current row is `<tr>`; make it conditional, and augment the password cell. Replace the password `<td>` block:

```html
      <td>
        {% if r.password %}
        <button class="redact" type="button" aria-pressed="false" aria-label="Reveal redacted value">
          <span class="bar">redacted</span><span class="v v--cred">{{ r.password }}</span>
        </button>
        {% else %}<span class="nil">—</span>{% endif %}
      </td>
```

with (and change `<tr>` to add the reused class):

```html
    {% set n = profile.reuse_counts.get(r.password) if profile and r.password else None %}
    <tr{% if n %} class="reused"{% endif %}>
```

(the `{% set %}` goes immediately before the `<tr>`; the existing `<tr>` line is replaced by the two lines above)

and the password cell becomes:

```html
      <td>
        {% if r.password %}
        <span class="pwcell">
          {% if n %}<span class="reuse-chip" style="background:{{ r.password | reuse_color }}" title="reused in {{ n }} breaches"></span>{% endif %}
          <button class="redact" type="button" aria-pressed="false" aria-label="Reveal redacted value">
            <span class="bar">redacted</span><span class="v v--cred">{{ r.password }}</span>
          </button>
          {% if n %}<span class="reuse-stamp" title="reused in {{ n }} breaches">↻ ×{{ n }}</span>{% endif %}
        </span>
        {% else %}<span class="nil">—</span>{% endif %}
      </td>
```

Note: the existing row currently begins `<tr>` on the line after `{% for r in records %}`. Ensure the `{% set n %}` line is inside the loop, before `<tr>`.

- [ ] **Step 4: Upgrade the summary line**

In `_results.html`, within the `{% if profile %}` `.dossier-meta` block, replace the `Reused` stat:

```html
  <span class="stat {% if profile.reused_passwords %}stat--alert{% endif %}">Reused <b>{{ profile.reused_passwords | length }}</b></span>
```

with:

```html
  <span class="stat {% if profile.reuse_counts %}stat--alert{% endif %}">Reused <b>{{ profile.reuse_counts | length }}</b>{% if profile.reuse_counts %} · across <b>{{ profile.reuse_counts.values() | max }}</b> breaches{% endif %}</span>
```

- [ ] **Step 5: Add CSS**

Append to `src/static/app.css`:

```css
/* --- password reuse markers --------------------------------------------- */
.pwcell { display: inline-flex; align-items: center; gap: 0.4rem; }
.reuse-chip {
  width: 9px; height: 9px; border-radius: 2px; flex: none;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.3) inset;
}
.reuse-stamp {
  font-family: var(--cond);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-size: 0.6rem; font-weight: 600;
  color: var(--exposure);
  border: 1px solid var(--exposure);
  border-radius: 2px; padding: 0.02rem 0.35rem;
}
.ledger tr.reused td { background: rgba(229,72,77,0.05); }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_results_partial.py -k reused -v`
Expected: PASS. Also run the full file to confirm no regression: `pytest tests/test_results_partial.py -v`.

- [ ] **Step 7: Commit**

```bash
git add src/templates/_results.html src/static/app.css tests/test_results_partial.py
git commit -m "feat(ui): surface password reuse with per-row chip + stamp"
```

---

### Task 7: Copy-on-reveal affordance

**Files:**
- Modify: `src/templates/_results.html` (copy button inside each redact)
- Modify: `src/static/app.js` (copy handler)
- Modify: `src/static/app.css` (`.copy` visibility tied to `.revealed`)
- Test: `tests/test_results_partial.py` (markup presence)

**Interfaces:** presentational; JS behavior verified manually.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_results_partial.py`:

```python
def test_revealable_cell_has_copy_control():
    rec = SimpleNamespace(email="a@b.com", username="u", password="pw",
                          hashed_password=None, database_name="LeakA")
    profile = SimpleNamespace(reuse_counts={}, breach_sources={"LeakA": 1},
                              reused_passwords=[], hash_types={})
    html = _render_with_profile([rec], profile)
    assert 'class="copy"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_results_partial.py::test_revealable_cell_has_copy_control -v`
Expected: FAIL (no copy control).

- [ ] **Step 3: Add copy button to both redact cells**

In `src/templates/_results.html`, inside BOTH the password `.redact` button's parent and the hash cell, add a sibling copy button after each `</button>` that closes a `.redact`. For the password cell (inside `.pwcell`, after the redact `</button>` and before the optional stamp):

```html
          <button class="copy" type="button" aria-label="Copy value" data-copy="{{ r.password }}" hidden>copy</button>
```

For the hash cell, change:

```html
        <button class="redact" type="button" aria-pressed="false" aria-label="Reveal redacted value">
          <span class="bar">redacted</span><span class="v">{{ r.hashed_password }}</span>
        </button><span class="stamp">{{ r.hashed_password | hash_type }}</span>
```

to add a copy button before the `<span class="stamp">`:

```html
        <button class="redact" type="button" aria-pressed="false" aria-label="Reveal redacted value">
          <span class="bar">redacted</span><span class="v">{{ r.hashed_password }}</span>
        </button><button class="copy" type="button" aria-label="Copy value" data-copy="{{ r.hashed_password }}" hidden>copy</button><span class="stamp">{{ r.hashed_password | hash_type }}</span>
```

(`data-copy` is autoescaped by Jinja — safe.)

- [ ] **Step 4: Show copy only after reveal**

The copy button is adjacent to its `.redact`. Update `app.js` to toggle the sibling copy button's visibility on reveal, and handle copy clicks. Replace `src/static/app.js` contents with:

```javascript
// Redaction reveal + copy-on-reveal. Event-delegated so it survives HTMX swaps.
document.addEventListener("click", (e) => {
  const redact = e.target.closest(".redact");
  if (redact) {
    const revealed = redact.classList.toggle("revealed");
    redact.setAttribute("aria-pressed", revealed ? "true" : "false");
    redact.setAttribute("aria-label", revealed ? "Hide value" : "Reveal redacted value");
    // The copy control is the redact's next sibling (or next-next, past a chip/stamp).
    const copy = redact.parentElement
      ? redact.parentElement.querySelector(".copy")
      : null;
    if (copy) copy.hidden = !revealed;
    return;
  }
  const copy = e.target.closest(".copy");
  if (copy) {
    const val = copy.getAttribute("data-copy") || "";
    navigator.clipboard.writeText(val).then(() => {
      const prev = copy.textContent;
      copy.textContent = "copied";
      setTimeout(() => { copy.textContent = prev; }, 1200);
    });
  }
});
```

Note: for the password cell the `.copy` lives inside `.pwcell` (same parent as `.redact`); for the hash cell it is a direct sibling within the `<td>`. `redact.parentElement.querySelector(".copy")` finds it in both layouts.

- [ ] **Step 5: Add CSS**

Append to `src/static/app.css`:

```css
.copy {
  font-family: var(--cond);
  text-transform: uppercase; letter-spacing: 0.08em;
  font-size: 0.6rem;
  color: var(--amber);
  border: 1px solid var(--amber-dim);
  background: rgba(224,163,62,0.07);
  border-radius: 2px; padding: 0.02rem 0.35rem;
  margin-left: 0.4rem; cursor: pointer;
}
.copy:hover { background: rgba(224,163,62,0.18); }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_results_partial.py::test_revealable_cell_has_copy_control -v`
Expected: PASS.

- [ ] **Step 7: Verify behavior (manual)**

In the render-harness browser: reveal a password → "copy" appears → click → clipboard holds the value and the button flashes "copied". Hide → "copy" disappears.

- [ ] **Step 8: Commit**

```bash
git add src/templates/_results.html src/static/app.js src/static/app.css tests/test_results_partial.py
git commit -m "feat(ui): copy-on-reveal control for redacted secrets"
```

---

## Track 3 — Mobile / responsive (P3)

### Task 8: `data-label` attributes for card layout

**Files:**
- Modify: `src/templates/_results.html` (add `data-label` to each `<td>`)
- Modify: `src/templates/audit.html` (add `data-label` to each `<td>`)
- Test: `tests/test_results_partial.py` (assert labels present)

**Interfaces:** presentational; consumed by Task 9 CSS.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_results_partial.py`:

```python
def test_result_cells_have_data_labels():
    rec = SimpleNamespace(email="a@b.com", username="u", password=None,
                          hashed_password=None, database_name="LeakA")
    profile = SimpleNamespace(reuse_counts={}, breach_sources={"LeakA": 1},
                              reused_passwords=[], hash_types={})
    html = _render_with_profile([rec], profile)
    assert 'data-label="Email"' in html
    assert 'data-label="Source"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_results_partial.py::test_result_cells_have_data_labels -v`
Expected: FAIL.

- [ ] **Step 3: Add data-labels to `_results.html`**

Add `data-label="..."` to each `<td>` matching its `<th>`: `Email`, `Username`, `Password`, `Hash`, `Source`, and the pivot cell `data-label=""` (no label). E.g. `<td data-label="Email">{{ r.email or "" }}</td>`, etc.

- [ ] **Step 4: Add data-labels to `audit.html`**

Add `data-label` to each `<td>`: `Timestamp`, `Action`, `Query`, `Cost`.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_results_partial.py::test_result_cells_have_data_labels -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/templates/_results.html src/templates/audit.html tests/test_results_partial.py
git commit -m "feat(ui): add data-label attrs to ledger cells for mobile cards"
```

---

### Task 9: Responsive card layout + header fixes

**Files:**
- Modify: `src/static/app.css` (rework the `max-width: 640px` block; `.subject .id` wrap)
- Test: visual verification (no unit test — CSS only)

**Interfaces:** presentational.

- [ ] **Step 1: Fix subject wrap**

In `src/static/app.css`, in `.subject .id`, replace `word-break: break-all;` with:

```css
  overflow-wrap: anywhere;
```

- [ ] **Step 2: Rework the responsive block**

Replace the existing `@media (max-width: 640px) { ... }` block with:

```css
@media (max-width: 640px) {
  .masthead { padding: 0.75rem 1rem; }
  .brand .sub { display: none; }
  .sheet { padding: 1.6rem 1rem 3rem; }

  /* keep masthead a single row */
  .mast-nav { gap: 0.9rem; }
  .status .label, .status > :not(.dot) { display: none; }

  /* ledger -> stacked cards */
  .ledger, .ledger thead, .ledger tbody, .ledger tr, .ledger td { display: block; }
  .ledger thead { display: none; }
  .ledger tr {
    border: 1px solid var(--hairline);
    border-radius: var(--r);
    margin-bottom: 0.7rem;
    padding: 0.2rem 0.6rem;
  }
  .ledger tbody td {
    border-bottom: 1px dashed var(--hairline);
    display: flex; justify-content: space-between; gap: 1rem;
    padding: 0.5rem 0.2rem; white-space: normal; text-align: right;
  }
  .ledger tbody tr td:last-child { border-bottom: 0; }
  .ledger tbody td::before {
    content: attr(data-label);
    font-family: var(--cond);
    text-transform: uppercase; letter-spacing: 0.1em;
    font-size: 0.62rem; color: var(--muted);
    text-align: left; flex: none;
  }
  .ledger tbody td[data-label=""]::before { content: ""; }
}
```

Note on the masthead status: the markup is `<span class="status"><span class="dot"></span> Restricted</span>` — the text "Restricted" is a bare text node, not wrappable by `:not(.dot)`. To hide it cleanly, wrap the label in Task 9 Step 3.

- [ ] **Step 3: Wrap the status label so it can hide**

In `src/templates/base.html`, change:

```html
      <span class="status"><span class="dot" aria-hidden="true"></span> Restricted</span>
```

to:

```html
      <span class="status"><span class="dot" aria-hidden="true"></span> <span class="label">Restricted</span></span>
```

(The CSS `.status .label { display: none }` in the responsive block now hides it; remove the unreliable `:not(.dot)` selector from Step 2's block, keeping only `.status .label { display: none; }`.)

- [ ] **Step 4: Verify visually at 390px and 1280px (manual)**

Using the render-harness + Playwright (or live app): at 390px the results and audit ledgers render as stacked labeled cards (no horizontal scroll), the subject email wraps at sensible points, and the masthead stays one row. At 1280px the table layout is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/static/app.css src/templates/base.html
git commit -m "feat(ui): mobile card layout for ledgers + masthead/subject fixes"
```

---

## Final: quality gate + branch finish

- [ ] **Step 1: Run the full gate**

Run: `black . && ruff check . && mypy && pytest`
Expected: all clean. (Requires Postgres for the DB-backed tests.)

- [ ] **Step 2: Finish the branch**

Use the `superpowers:finishing-a-development-branch` skill to decide merge/PR/cleanup.

---

## Self-Review

**Spec coverage:**
- Track 1.1 pending state → Task 1. 1.2 favicon → Task 2. 1.3 empty-target chrome → Task 3. 1.4 selector default → Task 3. ✓
- Track 2.1 data layer → Task 4. 2.2 row markers + summary → Task 6 (chip color filter → Task 5). 2.3 copy affordance → Task 7. 2.4 tests → Tasks 4 & 6 & 7. ✓
- Track 3.1 card layout → Tasks 8 & 9. 3.2 subject wrap → Task 9. 3.3 masthead → Task 9. ✓
- Cross-cutting: gate + branch finish → Final. Environment prerequisite called out in Global Constraints. ✓

**Type consistency:** `reuse_counts: dict[str, int]` defined in Task 4, consumed identically in Tasks 5/6. `reuse_color(password: str) -> str` defined in Task 5, used as `| reuse_color` filter in Task 6. `data-label` strings in Task 8 match `td::before { content: attr(data-label) }` in Task 9. ✓

**Placeholder scan:** No TBD/TODO; every code step shows actual code. The one self-correcting note (Task 1 `::after` label approach) resolves to a concrete final implementation. ✓
