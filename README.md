# DeHashed OSINT Platform

A FastAPI-based OSINT investigation platform that queries the DeHashed v2 API,
persists and correlates leaked-data records, and exports intelligence reports as
CSV, JSON, or PDF.

## Authorization / Leaked-Data Disclaimer

This tool is intended solely for **authorized investigations** — e.g., your own
accounts, accounts you have explicit written permission to research, or law-
enforcement/legal contexts where applicable law permits the access. Querying
DeHashed for data about individuals without authorization may violate the
Computer Fraud and Abuse Act (18 U.S.C. § 1030), state computer-crime statutes,
and/or the DeHashed Terms of Service. You are solely responsible for ensuring
lawful use.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 or later |
| Docker (for Postgres) | any recent version |
| DeHashed API key | paid account at dehashed.com |

---

## Setup

```bash
# 1. Copy the example env file and fill in your values
cp .env.example .env

# 2. Generate a 32-byte base64 ENCRYPTION_KEY and paste into .env
python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"

# 3. Start Postgres
docker compose up -d postgres

# 4. Install Python dependencies
poetry install

# 5. Apply database migrations
poetry run alembic upgrade head
```

---

## Run

```bash
poetry run uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000
```

Interactive API docs are available at <http://127.0.0.1:8000/docs>.

---

## Test

```bash
poetry run pytest
```

---

## Quality Gate

```bash
poetry run black . && poetry run ruff check . && poetry run mypy && poetry run pytest
```

All four tools must exit 0 before merging.

---

## Export Endpoints

| Endpoint | Content-Type | Notes |
|---|---|---|
| `GET /v1/targets/{id}/export.csv` | `text/csv` | All result records as CSV |
| `GET /v1/targets/{id}/export.json` | `application/json` | All result records as JSON |
| `GET /v1/targets/{id}/report.pdf` | `application/pdf` | Correlated TargetProfile report |

PDF generation uses **ReportLab** (pure-Python, no native binary dependencies).
WeasyPrint is not used in this project.
