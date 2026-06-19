# DeHashed OSINT Platform — Design Spec

**Date:** 2026-06-18
**Status:** Approved (pending implementation plan)
**Owner:** Landon Mayo

---

## 1. Purpose

A web-based OSINT platform that wraps the DeHashed API (v2) to surface leaked
credential and PII data on authorized investigation targets. Work is organized
into structured investigations, with an intelligence layer (pivoting,
correlation, credential analysis, breach-source mapping) on top of raw API
results. Built for a solo operator now, architected so multi-user support is
later wiring rather than a rewrite.

> **Authorization notice:** This tool surfaces real leaked PII. All use is
> assumed to be authorized security testing / OSINT work. The platform enforces
> a one-time authorization acknowledgment and keeps an append-only audit log as
> the engagement record.

---

## 2. Approach & Stack

A **FastAPI monolith** serving both a versioned JSON API (`/v1/...`) and
server-rendered HTMX pages from one process. One deployable, one language, no
JS build pipeline. The pivot graph — the only genuinely visual feature — uses a
small embedded JS library (Cytoscape.js) fed by a JSON endpoint; everything
else is HTMX partials.

| Layer        | Choice                                                    |
| ------------ | --------------------------------------------------------- |
| API + web    | FastAPI (async), Jinja2 + HTMX                            |
| Graph viz    | Cytoscape.js (pivot view only)                            |
| DB           | PostgreSQL via SQLAlchemy 2.0 async (`asyncpg`) + Alembic |
| HTTP client  | `httpx` async (DeHashed calls)                            |
| Config       | `pydantic-settings`                                       |
| Logging      | `structlog` with a PII/credential-redaction processor     |
| Crypto       | App-layer AES-GCM for sensitive columns                   |
| Reports      | WeasyPrint (HTML→PDF, reuses Jinja templates)             |
| Runtime      | docker-compose: `app` + `postgres`                        |

**Rejected alternative — React/Vue SPA:** richer, but adds a build toolchain and
a second codebase for marginal gain when HTMX covers tables/forms/partials and
Cytoscape handles the one graph. Revisit only if the UI outgrows HTMX.

---

## 3. DeHashed API v2 — Integration Facts

- **Auth:** API key passed in a request header. Credit-based billing — each
  search consumes credits; the response returns remaining `balance`.
- **Search:** `POST` with a JSON body: `query`, `page`, `size`, and flags
  including `wildcard` / `regex`. Queries are effectively OR-based.
- **Searchable fields:** `field:value` syntax over email, username, password,
  hashed_password, name, ip_address, phone, address, domain, vin, etc.
- **Response:** `entries[]` (per-record breach fields) + `total` + remaining
  `balance`.
- **Known caveat:** wildcard and regex search have been unreliable in v2. They
  are exposed in the UI but flagged **experimental** and degrade gracefully.

---

## 4. Data Model

Multi-user-ready, auth stubbed. An `owner_id` FK lives on every top-level row
from day one, pointing at a `users` stub table seeded with a single local user.
Adding real auth later is wiring, not a migration.

```
users            (id, …stub…)
investigations   (id, owner_id, name, status, notes, created_at)
targets          (id, investigation_id, label, entity_type)
selectors        (id, target_id, field_type, value)        # seed identifiers: email/username/ip/phone…
searches         (id, target_id, query, params, cache_key,
                  cost, balance_after, status, took, created_at)
result_records   (id, search_id, target_id, raw_json,
                  email, username, password*, hashed_password*,
                  name*, ip_address, phone*, address*, database_name, …)
audit_log        (id, owner_id, action, query, cost, ts)    # append-only
```

`*` = AES-GCM encrypted at the app layer before write (key from env,
KMS-swappable). Correlation profiles are **computed on read** from
`result_records` — no materialized table until read-time computation proves too
slow.

---

## 5. Services (`src/services`)

- **`DehashedClient`** (`repositories/external`) — async httpx; auth header;
  retry/backoff on 429/5xx; maps the API response → normalized records; returns
  `total` + remaining `balance`. Wildcard/regex exposed but flagged
  experimental and degraded gracefully.
- **`SearchService`** — builds the query (whitelisted field names, escaped
  values), checks **cache** (`cache_key` = hash of normalized query → skip
  credit spend on repeats), runs the **credit-guard** (warn/refuse below a
  configurable balance threshold), persists search + records, writes the audit
  entry.
- **`CorrelationService`** — dedup/merge records into a per-target profile;
  **credential analysis** (hash-type identification + password-reuse flagging);
  **breach-source mapping** grouped by `database_name`.
- **`PivotService`** — turns any result field into a ready-to-run seeded search
  (the OSINT loop).
- **`ReportService`** — PDF (WeasyPrint) + CSV/JSON export.

---

## 6. Data Flow — The Pivot Loop

1. Create investigation → add a target with seed selectors.
2. Run search → `SearchService`: cache check → credit-guard → `DehashedClient`
   → normalize → encrypt sensitive fields → persist records/search/audit.
3. Results render as an HTMX partial; correlation recomputes the target profile.
4. Click any field → `PivotService` seeds a new search → back to step 2.
5. Export / generate PDF when done.

---

## 7. Error Handling

Specific domain exceptions: `DehashedAuthError`, `DehashedRateLimitError`,
`InsufficientCreditsError`, `DehashedAPIError`. Backoff + retry on transient
429/5xx; surface 4xx verbatim to the UI. The credit-guard is **pre-flight** —
it refuses to spend below the configured threshold. The structlog redaction
processor guarantees no query values, passwords, or PII reach logs.

---

## 8. Security & Legal Posture

- DeHashed key in env via `pydantic-settings` — never in source or logs.
- App-layer AES-GCM on passwords / hashes / PII columns.
- Local-bind (`127.0.0.1`) by default; secure response headers.
- Input sanitization on the query builder (field whitelist, value escaping).
- **Authorization gate:** one-time acknowledgment that searches are authorized,
  plus the append-only audit log as the engagement record.

---

## 9. Testing

`pytest` + `pytest-asyncio`; `respx` to mock DeHashed; a test Postgres
(testcontainers) for the repo layer. Unit coverage on the query builder,
dedup/correlation, hash-type identification, credit-guard, and the encryption
round-trip. Contract test: real DeHashed response shape → normalizer. Templates
are not unit-tested.

---

## 10. Project Structure

```
src/
  api/          # /v1 JSON routes + HTMX page/partial routes
  services/     # SearchService, CorrelationService, PivotService, ReportService
  repositories/ # data access + external/DehashedClient
  schemas/      # Pydantic models
  core/         # config, logging, exceptions, crypto
  templates/    # Jinja2
  static/       # HTMX + Cytoscape.js assets
tests/
alembic/
docker-compose.yml
```

Start monolithic. Modularize when pain is real, not hypothetical.

---

## 11. Explicit Scope Cuts (YAGNI)

- **No bundled hash cracking.** Identify hash types and export to hashcat;
  in-app cracking is a separate concern, added later if needed.
- **No materialized correlation table** until read-time computation proves slow.
- **No real auth UI now** — just the `users` stub + `owner_id` plumbing.

---

## 12. Open Questions / Risks

- **Wildcard/regex reliability** in DeHashed v2 — treat as best-effort.
- **Credit burn** — caching + credit-guard mitigate, but identical-query
  detection depends on stable query normalization.
- **Encryption key management** — env-based key now; document the KMS migration
  path before any non-local deployment.
- **Data retention** — define a retention/purge policy for stored PII before the
  platform accumulates significant breach data.
