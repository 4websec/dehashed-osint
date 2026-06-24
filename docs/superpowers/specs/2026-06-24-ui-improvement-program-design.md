# UI Improvement Program — Design

**Date:** 2026-06-24
**Status:** Approved (design); pending implementation plan
**Scope:** The HTMX/Jinja web UI (`src/templates/`, `src/static/`, `src/api/web/pages.py`) and the
correlation data it renders (`src/services/correlation_service.py`, `src/schemas/domain.py`).

## Background

The "Redacted Dossier" UI is visually cohesive and well-executed: carbon + amber + exposure-red
palette, IBM Plex throughout, a redaction-bar reveal as the signature interaction, sensible empty
states, and good accessibility instincts (`aria-pressed`, `focus-visible`, `prefers-reduced-motion`,
escaped user input). A hands-on test of every screen (rendered with representative mock data and
driven in a browser at 1280px and 390px) surfaced a focused set of gaps. This program fixes them in
three independently-shippable tracks, sequenced by ascending effort.

Each track is a separate commit and passes the quality gate (`black . && ruff check . && mypy &&
pytest`) on its own.

---

## Track 1 — Search feedback & polish (P1)

Smallest surface, pure correctness wins, no new data flows.

### 1.1 Search pending state
**Problem:** `Run search` POSTs to DeHashed (network, up to a 30s timeout) with zero feedback — the
page appears frozen.

**Design:** The bundled HTMX supports `hx-indicator` and `hx-disabled-elt` (both verified present in
`src/static/htmx.min.js`).
- Add `hx-disabled-elt="this"` to the search submit button so it disables for the duration of the
  request.
- Add an inline spinner `<span class="spin" aria-hidden="true">` inside the button, shown only while
  the request is in flight. HTMX toggles the `htmx-request` class on the indicated element; CSS
  reveals the spinner on `.htmx-request` and swaps the button label to a "Searching…" state.
- The search form is the indicator target (default `hx-indicator` is the requesting element).

**Files:** `src/templates/target.html` (button markup), `src/static/app.css` (`.spin`, `.htmx-request`
rules). No backend change.

### 1.2 Favicon
**Problem:** `GET /favicon.ico` 404s (observed in console).

**Design:** Ship `src/static/favicon.svg` — the amber skewed-bar mark from `.brand` — and add
`<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">` to `base.html`. Served by the
existing static mount.

**Files:** `src/static/favicon.svg` (new), `src/templates/base.html`.

### 1.3 Hide export chrome on empty targets
**Problem:** The PDF/CSV/JSON export toolbar and pivot-graph link render even when a target has zero
records — you can "export" nothing.

**Design:** Wrap the report/export `.toolbar` in `{% if records %}` in `target.html`. The field
manual (`.manual`) stays unconditionally — it is instructional and useful before the first search.

**Files:** `src/templates/target.html`.

### 1.4 Selector default
**Problem:** The selector defaults to `address` (alphabetically first from `sorted(ALLOWED_FIELDS)`),
not the common entry points.

**Design:** Mark `email` as the `selected` option in the `<select>` (template-level conditional;
no change to the `fields` list passed from `pages.py`).

**Files:** `src/templates/target.html`.

---

## Track 2 — Surface password reuse (P2)

Highest analytic value. Treatment **Option A + copy affordance** (chosen from three mocked
alternatives). Reuse must be visible **while passwords are still redacted** — you should not have to
reveal every cell to spot correlation.

### 2.1 Data layer
**Current:** `CorrelationService.build_profile` builds `pw_breaches: dict[str, set[str]]` (password →
set of distinct breach sources) and derives `reused_passwords = [pw for pw, srcs in pw_breaches if
len(srcs) > 1]`. `TargetProfile` exposes only the flat `reused_passwords` list — no per-row count.

**Design:** Add a field to `TargetProfile`:
```python
reuse_counts: dict[str, int] = Field(default_factory=dict)  # password -> distinct breach-source count, reused only
```
Populate it in `build_profile` from the existing `pw_breaches` map:
`{pw: len(srcs) for pw, srcs in pw_breaches.items() if len(srcs) > 1}`. Keep `reused_passwords` for
back-compat (derivable from `reuse_counts.keys()`).

Reuse semantics are unchanged: same plaintext password under **>1 distinct breach source**.

**Files:** `src/schemas/domain.py`, `src/services/correlation_service.py`.

### 2.2 Row markers (`_results.html`)
For each record where `r.password` is truthy and `r.password in profile.reuse_counts`:
- Add a `reused` class to the `<tr>` → subtle exposure-red row tint (`tr.reused td`).
- Render a small **group color chip** before the redaction bar and a `↻ ×N` **reuse stamp** after it,
  where `N = profile.reuse_counts[r.password]`. Neither reveals the plaintext.
- The exposure-red tint is the shared "this is reused" signal. When **multiple distinct** reused
  passwords exist, the chip color differentiates *which* one: a deterministic hue derived from the
  password (a Jinja filter `reuse_color(pw)` mapping to a small fixed on-brand palette / hue). With a
  single reused password the chip is exposure-red (matching the row tint); the deterministic hue only
  comes into play to disambiguate when two or more distinct reused passwords are present.

The aggregate summary in `.dossier-meta` is upgraded to read e.g. "Reused **1** password across
**3** breaches" using `reuse_counts`.

**Files:** `src/templates/_results.html`, a Jinja filter registered in `src/api/web/pages.py`
(alongside the existing `hash_type` filter), `src/static/app.css`.

### 2.3 Copy affordance (`app.js`)
A `copy` control that appears **only once a `.redact` is revealed** (CSS shows it on
`.redact.revealed`, hidden otherwise). On click: `navigator.clipboard.writeText(<revealed value>)`,
brief "copied" feedback (transient class/text), and an `aria-label`. Event-delegated like the
existing reveal handler so it survives HTMX row swaps. No extra column, no per-row clutter on
unrevealed/empty cells.

**Files:** `src/templates/_results.html` (copy button markup inside each redact), `src/static/app.js`,
`src/static/app.css` (`.copy`, `.reuse-stamp`, group chip, `tr.reused td`).

### 2.4 Tests
- Extend the correlation service test: assert `reuse_counts` is populated correctly (a password under
  2+ sources appears with its count; a password under a single source does not).
- Extend `tests/test_results_partial.py`: given records with a reused password, the rendered partial
  marks the affected rows (`reused` class / `↻ ×N` stamp present); with no reuse, no marker.

---

## Track 3 — Mobile / responsive (P3)

Largest surface. Phone is a plausible field-use context; the data-dense ledger currently
overflow-scrolls so Source/Pivot fall off-screen.

### 3.1 Card-layout ledger < 640px
**Design:** Replace the `overflow-x: auto` ledger behavior in the `max-width: 640px` block with a
responsive card transform. Each `<td>` carries a `data-label` attribute; under the breakpoint the
table, rows, and cells become `display: block`, and `td::before { content: attr(data-label) }`
renders the column name beside each value — every record becomes a self-contained labeled card. Apply
to both the results ledger (`_results.html`) and the audit ledger (`audit.html`).

**Files:** `src/templates/_results.html` and `src/templates/audit.html` (`data-label` attributes),
`src/static/app.css` (responsive block).

### 3.2 Subject header wrap
**Problem:** `.subject .id { word-break: break-all }` breaks the subject email mid-token
("gmail.co/m").

**Design:** Use `overflow-wrap: anywhere` (break at sensible boundaries, fall back to anywhere only
when needed) instead of `word-break: break-all`.

**Files:** `src/static/app.css`.

### 3.3 Masthead on narrow screens
**Problem:** At ~390px the nav ("Audit log") wraps to two lines.

**Design:** In the responsive block, shrink `.mast-nav` gaps and hide the "Restricted" status *text*
(keep the pulsing dot) so the masthead stays a single row. The `.brand .sub` is already hidden < 640px.

**Files:** `src/static/app.css`.

---

## Cross-cutting concerns

### Sequencing
P1 → P2 → P3 (ascending effort, descending certainty). Each track is a discrete commit and ships
independently.

### Verification
- **Automated:** `black . && ruff check . && mypy && pytest` must pass for each track. New tests per
  Track 2 (§2.4). `alembic/` remains excluded from ruff/mypy.
- **Visual/responsive:** the render-harness used during design (real templates + `app.css` + `app.js`
  rendered with mock data, served and driven via Playwright at 1280px and 390px) verifies layout, the
  reveal/copy interactions, reuse markers, and the mobile card layout without spending DeHashed
  credits.

### Environment prerequisite (⚠ blocker for the gate)
`pytest` requires a running Postgres (conftest auto-creates `osint_test`). At design time **Docker is
down and Poetry's environment points at a missing Python interpreter**. Before the quality gate can
run, the implementer must restore the local toolchain: start Docker/Postgres and repair the Poetry
interpreter. The render-harness verification does not need Postgres, but the gate does.

### Out of scope (deliberately deferred)
- Per-row search provenance (which query produced which row).
- Audit-log pagination/filtering.
- Pivot on selectors other than `email`.
- Authentication changes (the `/v1` API is intentionally unauthenticated; `/ui` is cookie-gated).
- Low-contrast audit of muted labels (`#7c8794` on carbon) — noted during testing, not addressed here.
