# DeHashed OSINT Platform — Project Context

FastAPI + HTMX OSINT console wrapping the DeHashed v2 API. Postgres-backed,
app-layer AES-GCM encryption. Python 3.11+, Poetry, Docker. Follows the global
engineering standards in ~/.claude/CLAUDE.md.

## Commands
```bash
docker compose up -d postgres                      # start DB (creds osint/osint, db "osint")
poetry install                                     # deps only (package-mode = false)
poetry run alembic upgrade head                    # migrations
poetry run uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000
poetry run pytest                                  # tests (use a SEPARATE osint_test DB)
black . && ruff check . && mypy && pytest          # quality gate — must pass before commit
```

## Architecture
- `src/api/v1/` JSON API (`/v1/...`), `src/api/web/pages.py` HTMX routes, `src/templates/` Jinja, `src/static/` (app.css = "Redacted Dossier" design system, app.js = redaction reveal)
- `src/services/` (search, correlation, pivot, report, query_builder), `src/repositories/` (+ `external/dehashed.py` client), `src/models.py`, `src/core/` (config, db, crypto, exceptions, logging)
- Specs/plans in `docs/superpowers/`. Session progress ledger in `.git/sdd/progress.md`.

## Gotchas (non-obvious — read before changing things)
- **Tests use a separate `osint_test` database** (auto-created by conftest; overridable via `TEST_DATABASE_URL`). The per-test `_clean_db` fixture TRUNCATEs. **Never run TRUNCATE against the app's `osint` DB — it destroys real investigation data.**
- **`/v1` API is intentionally unauthenticated** (exempt from the auth-gate middleware; solo/local tool). `/ui` routes are gated by the `osint_authorized` cookie.
- **DeHashed v2 returns fields as arrays** (`email: ["x"]`). `RawEntry` flattens them to `str | None`; a parse failure raises `DehashedAPIError` (don't let it 500).
- **PDF = ReportLab, not WeasyPrint** (WeasyPrint can't load native libs on Windows). Escape values into ReportLab `Paragraph` via `xml.sax.saxutils.escape`.
- **Sensitive columns are AES-GCM encrypted** app-side (incl. `result_records.raw_json`). `.env` needs `DEHASHED_API_KEY` and base64-32-byte `ENCRYPTION_KEY`.
- **Windows + asyncpg:** use `TestClient` as a context manager (`with TestClient(app) as c:`) so the loop survives across requests.
- **HTMX `hx-vals` with dynamic data:** `{{ {...} | tojson | forceescape }}` in a double-quoted attr (raw `tojson` quotes break the attribute → JSON error/422).
- **`alembic/` is excluded** from ruff + mypy (generated code).
- **Credit-guard reads post-call balance** (guards future spend, not the current call).
- **Implementers must actually run `ruff`/`mypy`/`pytest`** and paste output — "clean by inspection" has broken the gate before.

## Use Context7
Default to the Context7 MCP server for library/framework/API documentation
lookups (FastAPI, SQLAlchemy, pydantic, HTMX, ReportLab, etc.) before writing
non-trivial code against a library. Per user standing preference.
