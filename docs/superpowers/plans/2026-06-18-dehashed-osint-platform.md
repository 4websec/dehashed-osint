# DeHashed OSINT Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI + HTMX web platform that wraps the DeHashed v2 API for authorized OSINT investigations, with a persistence + intelligence layer (pivoting, correlation, credential analysis, breach-source mapping), credit-guard + caching, audit logging, and PDF/CSV/JSON export.

**Architecture:** A FastAPI monolith serves both a versioned JSON API (`/v1/...`) and server-rendered HTMX pages from one process. PostgreSQL via async SQLAlchemy 2.0 stores investigations → targets → searches → result_records, with sensitive columns encrypted at the app layer (AES-GCM). The DeHashed integration is an isolated async httpx client; business logic lives in services consumed by both API and web routes.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2 + HTMX, Cytoscape.js, SQLAlchemy 2.0 (async, asyncpg), Alembic, httpx, pydantic-settings, structlog, cryptography (AES-GCM), WeasyPrint, pytest + pytest-asyncio + respx, Poetry, docker-compose.

## Global Constraints

- **Python:** 3.11+ (use `X | Y` union syntax, `Literal`, `TypedDict`).
- **Formatting/lint:** `black` (line length 88), `ruff`, `mypy --strict` on `src/`. Pre-commit order: black → ruff → mypy.
- **Typing:** annotate all function signatures and public variables.
- **Secrets:** DeHashed API key and encryption key come from env via `pydantic-settings` only — never hardcoded, never logged.
- **Logging:** `structlog` with a redaction processor; never log query values, passwords, hashes, or PII.
- **Errors:** specific exceptions only — no bare `except:`. Custom domain exception classes.
- **DB:** PostgreSQL only; all DB access async via SQLAlchemy 2.0 `AsyncSession`.
- **Encryption:** sensitive columns (`password`, `hashed_password`, `name`, `phone`, `address`) encrypted app-side via AES-GCM before write.
- **Multi-user-ready:** every top-level table carries `owner_id` FK to a seeded `users` stub; no auth UI is built.
- **Bind:** app binds `127.0.0.1` by default (configurable).
- **Commits:** conventional-commit messages, one commit per completed task minimum.

---

## File Structure

```
pyproject.toml                         # Poetry, black/ruff/mypy config
docker-compose.yml                     # app + postgres
.env.example                           # documented env vars
alembic.ini                            # Alembic config
alembic/env.py                         # async migration env
src/
  main.py                              # FastAPI app factory + router mounts
  core/
    config.py                          # Settings (pydantic-settings)
    logging.py                         # structlog config + redaction processor
    exceptions.py                      # domain exception hierarchy
    crypto.py                          # FieldCipher (AES-GCM) + EncryptedString type
    db.py                              # async engine, session maker, Base, get_session
  models.py                            # all ORM models
  schemas/
    dehashed.py                        # RawEntry, SearchResponse pydantic models
    domain.py                          # NormalizedRecord, TargetProfile, PivotSuggestion
  repositories/
    external/dehashed.py               # DehashedClient (httpx)
    investigations.py                  # InvestigationRepository
    searches.py                        # SearchRepository + ResultRecordRepository
  services/
    query_builder.py                   # field whitelist, query normalize, cache_key
    search_service.py                  # cache + credit-guard + persist + audit
    correlation_service.py             # dedup, hash-type id, reuse, breach mapping
    pivot_service.py                   # field -> seeded search suggestion
    report_service.py                  # CSV/JSON/PDF export
  api/
    v1/investigations.py               # JSON CRUD
    v1/searches.py                     # JSON run-search + results + pivot graph
    web/pages.py                       # HTMX pages + partials
  templates/                           # Jinja2 (+ HTMX, Cytoscape view)
  static/                              # htmx.min.js, cytoscape.min.js, app.css
tests/
  conftest.py                          # fixtures: settings, db session, respx
  ...                                  # mirrors src/ layout
```

---

## Task 1: Project scaffolding, config, and redacting logger

**Files:**
- Create: `pyproject.toml`, `.env.example`, `src/__init__.py`, `src/core/__init__.py`, `src/core/config.py`, `src/core/logging.py`
- Test: `tests/core/test_config.py`, `tests/core/test_logging.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings) with fields `dehashed_api_key: SecretStr`, `dehashed_base_url: str`, `database_url: str`, `encryption_key: SecretStr`, `credit_guard_threshold: int`, `app_host: str`, `app_port: int`. `get_settings() -> Settings` (cached). `configure_logging() -> None`. Redaction processor `redact_sensitive(logger, method_name, event_dict) -> dict`.

- [ ] **Step 1: Initialize Poetry project and dependencies**

Run:
```bash
cd /d/dehashed
poetry init --no-interaction --name dehashed-osint --python "^3.11"
poetry add fastapi "uvicorn[standard]" jinja2 "sqlalchemy[asyncio]" asyncpg alembic httpx pydantic-settings structlog cryptography weasyprint python-multipart
poetry add --group dev pytest pytest-asyncio respx black ruff mypy
```

- [ ] **Step 2: Configure tooling in `pyproject.toml`**

Append:
```toml
[tool.black]
line-length = 88

[tool.ruff]
line-length = 88
target-version = "py311"
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "S"]

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Write `.env.example`**

```bash
DEHASHED_API_KEY=replace-me
DEHASHED_BASE_URL=https://api.dehashed.com/v2
DATABASE_URL=postgresql+asyncpg://osint:osint@localhost:5432/osint
# 32 raw bytes, base64-encoded: python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
ENCRYPTION_KEY=replace-with-base64-32-bytes
CREDIT_GUARD_THRESHOLD=100
APP_HOST=127.0.0.1
APP_PORT=8000
```

- [ ] **Step 4: Write the failing config test**

`tests/core/test_config.py`:
```python
from src.core.config import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("DEHASHED_API_KEY", "abc")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("ENCRYPTION_KEY", "a" * 44)
    settings = Settings()
    assert settings.dehashed_api_key.get_secret_value() == "abc"
    assert settings.credit_guard_threshold == 100  # default
    assert settings.app_host == "127.0.0.1"  # default
```

- [ ] **Step 5: Run test to verify it fails**

Run: `poetry run pytest tests/core/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.config'`

- [ ] **Step 6: Implement `src/core/config.py`**

```python
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration. Secrets never hardcoded."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dehashed_api_key: SecretStr
    dehashed_base_url: str = "https://api.dehashed.com/v2"
    database_url: str
    encryption_key: SecretStr  # base64-encoded 32 bytes
    credit_guard_threshold: int = 100
    app_host: str = "127.0.0.1"
    app_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 7: Run config test to verify it passes**

Run: `poetry run pytest tests/core/test_config.py -v`
Expected: PASS

- [ ] **Step 8: Write the failing logging redaction test**

`tests/core/test_logging.py`:
```python
from src.core.logging import redact_sensitive

REDACTED = "***REDACTED***"


def test_redacts_sensitive_keys():
    event = {
        "event": "search",
        "password": "hunter2",
        "hashed_password": "deadbeef",
        "query": "email:a@b.com",
        "email": "a@b.com",
        "phone": "555",
        "name": "Jane",
        "address": "1 St",
        "status": "ok",
    }
    out = redact_sensitive(None, "info", dict(event))
    for key in ("password", "hashed_password", "query", "email", "phone", "name", "address"):
        assert out[key] == REDACTED
    assert out["status"] == "ok"  # non-sensitive untouched
```

- [ ] **Step 9: Run test to verify it fails**

Run: `poetry run pytest tests/core/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 10: Implement `src/core/logging.py`**

```python
from typing import Any

import structlog

REDACTED = "***REDACTED***"
_SENSITIVE_KEYS = frozenset(
    {"password", "hashed_password", "query", "email", "phone", "name", "address"}
)


def redact_sensitive(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """structlog processor: redact PII/credential keys before output."""
    for key in _SENSITIVE_KEYS:
        if key in event_dict and event_dict[key] is not None:
            event_dict[key] = REDACTED
    return event_dict


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            redact_sensitive,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
```

- [ ] **Step 11: Run all tests to verify they pass**

Run: `poetry run pytest tests/core -v`
Expected: PASS (both files)

- [ ] **Step 12: Commit**

```bash
git add pyproject.toml poetry.lock .env.example src/ tests/
git commit -m "feat: project scaffolding, settings, redacting logger"
```

---

## Task 2: AES-GCM field encryption

**Files:**
- Create: `src/core/crypto.py`
- Test: `tests/core/test_crypto.py`

**Interfaces:**
- Consumes: `Settings.encryption_key` (base64 32 bytes).
- Produces: `class FieldCipher` with `encrypt(plaintext: str) -> str` and `decrypt(token: str) -> str` (token = base64 of `nonce(12) || ciphertext`). `EncryptedString` — a SQLAlchemy `TypeDecorator` that transparently encrypts on bind / decrypts on result, used by models in Task 4.

- [ ] **Step 1: Write the failing round-trip test**

`tests/core/test_crypto.py`:
```python
import base64
import os

import pytest

from src.core.crypto import FieldCipher

KEY = base64.b64encode(os.urandom(32)).decode()


def test_encrypt_decrypt_round_trip():
    cipher = FieldCipher(KEY)
    token = cipher.encrypt("hunter2")
    assert token != "hunter2"
    assert cipher.decrypt(token) == "hunter2"


def test_ciphertext_is_nondeterministic():
    cipher = FieldCipher(KEY)
    assert cipher.encrypt("x") != cipher.encrypt("x")  # random nonce


def test_decrypt_rejects_tampered_token():
    cipher = FieldCipher(KEY)
    token = cipher.encrypt("secret")
    tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(Exception):  # AES-GCM auth tag failure
        cipher.decrypt(tampered)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/core/test_crypto.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/core/crypto.py`**

```python
import base64
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import String, TypeDecorator

_NONCE_BYTES = 12


class FieldCipher:
    """AES-256-GCM authenticated encryption for individual field values."""

    def __init__(self, b64_key: str) -> None:
        key = base64.b64decode(b64_key)
        if len(key) != 32:
            raise ValueError("ENCRYPTION_KEY must decode to 32 bytes")
        self._aesgcm = AESGCM(key)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def decrypt(self, token: str) -> str:
        blob = base64.b64decode(token)
        nonce, ct = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        return self._aesgcm.decrypt(nonce, ct, None).decode()


class EncryptedString(TypeDecorator[str]):
    """Transparent column encryption. Cipher injected at engine setup."""

    impl = String
    cache_ok = True
    _cipher: FieldCipher | None = None

    @classmethod
    def configure(cls, cipher: FieldCipher) -> None:
        cls._cipher = cipher

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        assert self._cipher is not None, "EncryptedString.configure() not called"
        return self._cipher.encrypt(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        assert self._cipher is not None, "EncryptedString.configure() not called"
        return self._cipher.decrypt(str(value))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/core/test_crypto.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/crypto.py tests/core/test_crypto.py
git commit -m "feat: AES-GCM field encryption + EncryptedString column type"
```

---

## Task 3: Domain exceptions

**Files:**
- Create: `src/core/exceptions.py`
- Test: `tests/core/test_exceptions.py`

**Interfaces:**
- Produces: `DehashedError` (base), subclasses `DehashedAuthError`, `DehashedRateLimitError`, `DehashedAPIError`, and `InsufficientCreditsError(balance: int, threshold: int)`.

- [ ] **Step 1: Write the failing test**

`tests/core/test_exceptions.py`:
```python
import pytest

from src.core.exceptions import (
    DehashedAuthError,
    DehashedError,
    InsufficientCreditsError,
)


def test_subclasses_share_base():
    assert issubclass(DehashedAuthError, DehashedError)


def test_insufficient_credits_carries_context():
    exc = InsufficientCreditsError(balance=5, threshold=100)
    assert exc.balance == 5
    assert exc.threshold == 100
    assert "5" in str(exc) and "100" in str(exc)


def test_is_raisable():
    with pytest.raises(DehashedError):
        raise DehashedAuthError("bad key")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/core/test_exceptions.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/core/exceptions.py`**

```python
class DehashedError(Exception):
    """Base class for all DeHashed integration errors."""


class DehashedAuthError(DehashedError):
    """Authentication with the DeHashed API failed (401/403)."""


class DehashedRateLimitError(DehashedError):
    """DeHashed API returned 429 after retries."""


class DehashedAPIError(DehashedError):
    """Unexpected/non-2xx response from the DeHashed API."""


class InsufficientCreditsError(DehashedError):
    """Remaining balance is at or below the configured credit-guard threshold."""

    def __init__(self, balance: int, threshold: int) -> None:
        self.balance = balance
        self.threshold = threshold
        super().__init__(
            f"DeHashed balance {balance} at/below guard threshold {threshold}; "
            "refusing to spend credits."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/core/test_exceptions.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/exceptions.py tests/core/test_exceptions.py
git commit -m "feat: domain exception hierarchy"
```

---

## Task 4: Database engine, models, and migration

**Files:**
- Create: `src/core/db.py`, `src/models.py`, `docker-compose.yml`, `alembic.ini`, `alembic/env.py`, `alembic/versions/0001_initial.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `Settings.database_url`, `EncryptedString`, `FieldCipher`.
- Produces: `Base` (DeclarativeBase), `get_session()` async dependency, `make_engine(url)`. ORM models `User`, `Investigation`, `Target`, `Selector`, `Search`, `ResultRecord`, `AuditLog` with the columns from the spec. `SEED_USER_ID: int = 1`.

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: osint
      POSTGRES_PASSWORD: osint
      POSTGRES_DB: osint
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

- [ ] **Step 2: Implement `src/core/db.py`**

```python
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def make_session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


_session_maker: async_sessionmaker[AsyncSession] | None = None


def set_session_maker(maker: async_sessionmaker[AsyncSession]) -> None:
    global _session_maker
    _session_maker = maker


async def get_session() -> AsyncIterator[AsyncSession]:
    assert _session_maker is not None, "session maker not configured"
    async with _session_maker() as session:
        yield session
```

- [ ] **Step 3: Implement `src/models.py`**

```python
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.crypto import EncryptedString
from src.core.db import Base

SEED_USER_ID = 1


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(120), default="local")


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=SEED_USER_ID)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    targets: Mapped[list["Target"]] = relationship(back_populates="investigation", cascade="all, delete-orphan")


class Target(Base):
    __tablename__ = "targets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id"))
    label: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(40), default="person")
    investigation: Mapped["Investigation"] = relationship(back_populates="targets")
    selectors: Mapped[list["Selector"]] = relationship(back_populates="target", cascade="all, delete-orphan")


class Selector(Base):
    __tablename__ = "selectors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id"))
    field_type: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(400))
    target: Mapped["Target"] = relationship(back_populates="selectors")


class Search(Base):
    __tablename__ = "searches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id"))
    query: Mapped[str] = mapped_column(String(600))
    params: Mapped[str] = mapped_column(String(200), default="{}")
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    balance_after: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    took: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResultRecord(Base):
    __tablename__ = "result_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id"))
    raw_json: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    password: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(60), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    database_name: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=SEED_USER_ID)
    action: Mapped[str] = mapped_column(String(60))
    query: Mapped[str | None] = mapped_column(String(600), nullable=True)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Scaffold Alembic and write the initial migration**

Run: `poetry run alembic init alembic`

Edit `alembic/env.py` to set async target metadata: import `Base` from `src.core.db`, import `src.models` so tables register, set `target_metadata = Base.metadata`, and read the URL from `get_settings().database_url`. Then autogenerate:

Run:
```bash
docker compose up -d postgres
poetry run alembic revision --autogenerate -m "initial schema"
```
Expected: a migration appears under `alembic/versions/` creating all seven tables. Verify it includes `users`, `investigations`, `targets`, `selectors`, `searches`, `result_records`, `audit_log`.

- [ ] **Step 5: Write the failing model persistence test**

`tests/test_models.py` (uses the live local Postgres + a transaction rollback fixture defined in `tests/conftest.py`, Task 5 Step 1 — for now assume `db_session` fixture exists):
```python
import pytest

from src.models import Investigation, ResultRecord, Search, Target


@pytest.mark.asyncio
async def test_encrypted_password_round_trips(db_session):
    inv = Investigation(name="Op Test")
    db_session.add(inv)
    await db_session.flush()
    target = Target(investigation_id=inv.id, label="jane")
    db_session.add(target)
    await db_session.flush()
    search = Search(target_id=target.id, query="email:a@b.com", cache_key="k1")
    db_session.add(search)
    await db_session.flush()
    rec = ResultRecord(
        search_id=search.id, target_id=target.id, raw_json="{}", password="hunter2"
    )
    db_session.add(rec)
    await db_session.flush()
    db_session.expire(rec)
    loaded = await db_session.get(ResultRecord, rec.id)
    assert loaded is not None
    assert loaded.password == "hunter2"  # decrypted transparently
```

- [ ] **Step 6: Run migration against DB and the test**

Run:
```bash
poetry run alembic upgrade head
poetry run pytest tests/test_models.py -v
```
Expected: PASS (round-trip through `EncryptedString` works). If the conftest fixture isn't built yet, do Task 5 Step 1 first, then return here.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml alembic.ini alembic/ src/core/db.py src/models.py tests/test_models.py
git commit -m "feat: postgres engine, ORM models, initial migration"
```

---

## Task 5: Test harness (DB fixture + settings/cipher wiring)

**Files:**
- Create: `tests/conftest.py`
- Modify: `src/main.py` (app factory — created here, expanded later)
- Test: `tests/test_app_boot.py`

**Interfaces:**
- Produces: pytest fixtures `test_settings`, `db_session` (function-scoped, rolled back), and `configured_cipher` (calls `EncryptedString.configure`). `create_app() -> FastAPI` factory that calls `configure_logging()`, builds the engine/session-maker, configures the cipher, and mounts routers (routers added in later tasks).

- [ ] **Step 1: Implement `tests/conftest.py`**

```python
import base64
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import Settings
from src.core.crypto import EncryptedString, FieldCipher
from src.core.db import Base, make_engine, make_session_maker

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint"
)


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    return Settings(
        dehashed_api_key="test-key",
        database_url=TEST_DB_URL,
        encryption_key=base64.b64encode(os.urandom(32)).decode(),
        credit_guard_threshold=100,
    )


@pytest.fixture(scope="session", autouse=True)
def _configure_cipher(test_settings: Settings) -> None:
    EncryptedString.configure(
        FieldCipher(test_settings.encryption_key.get_secret_value())
    )


@pytest_asyncio.fixture
async def db_session(test_settings: Settings) -> AsyncIterator[AsyncSession]:
    engine = make_engine(test_settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = make_session_maker(engine)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()
```

- [ ] **Step 2: Implement minimal `src/main.py` app factory**

```python
from fastapi import FastAPI

from src.core.config import get_settings
from src.core.crypto import EncryptedString, FieldCipher
from src.core.db import make_engine, make_session_maker, set_session_maker
from src.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    EncryptedString.configure(FieldCipher(settings.encryption_key.get_secret_value()))
    engine = make_engine(settings.database_url)
    set_session_maker(make_session_maker(engine))

    app = FastAPI(title="DeHashed OSINT Platform")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

- [ ] **Step 3: Write the failing app-boot test**

`tests/test_app_boot.py`:
```python
from fastapi.testclient import TestClient

from src.main import create_app


def test_healthz(monkeypatch):
    monkeypatch.setenv("DEHASHED_API_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint")
    import base64, os
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    get_settings_cache_clear()
    client = TestClient(create_app())
    assert client.get("/healthz").json() == {"status": "ok"}


def get_settings_cache_clear():
    from src.core.config import get_settings
    get_settings.cache_clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry run pytest tests/test_app_boot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py src/main.py tests/test_app_boot.py
git commit -m "feat: test harness, db fixture, app factory"
```

---

## Task 6: Query builder (field whitelist, normalization, cache key)

**Files:**
- Create: `src/services/__init__.py`, `src/services/query_builder.py`
- Test: `tests/services/test_query_builder.py`

**Interfaces:**
- Produces: `ALLOWED_FIELDS: frozenset[str]`, `build_query(field: str, value: str) -> str` (raises `ValueError` on disallowed field), `normalize_query(query: str) -> str`, `cache_key(query: str, params: dict[str, object]) -> str` (sha256 hex).

- [ ] **Step 1: Write the failing test**

`tests/services/test_query_builder.py`:
```python
import pytest

from src.services.query_builder import (
    ALLOWED_FIELDS,
    build_query,
    cache_key,
    normalize_query,
)


def test_build_query_known_field():
    assert build_query("email", "a@b.com") == 'email:"a@b.com"'


def test_build_query_rejects_unknown_field():
    with pytest.raises(ValueError):
        build_query("ssn", "123")


def test_email_is_allowed():
    assert "email" in ALLOWED_FIELDS


def test_normalize_is_case_and_space_stable():
    assert normalize_query("  Email:A@B.com ") == normalize_query("email:a@b.com")


def test_cache_key_stable_and_param_sensitive():
    k1 = cache_key("email:a@b.com", {"page": 1})
    k2 = cache_key("email:a@b.com", {"page": 1})
    k3 = cache_key("email:a@b.com", {"page": 2})
    assert k1 == k2 and k1 != k3
    assert len(k1) == 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/services/test_query_builder.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/services/query_builder.py`**

```python
import hashlib
import json

ALLOWED_FIELDS: frozenset[str] = frozenset(
    {
        "email",
        "username",
        "password",
        "hashed_password",
        "name",
        "ip_address",
        "phone",
        "address",
        "domain",
        "vin",
    }
)


def build_query(field: str, value: str) -> str:
    """Build a single field:value clause. Whitelists field, quotes value."""
    if field not in ALLOWED_FIELDS:
        raise ValueError(f"Disallowed search field: {field!r}")
    escaped = value.replace('"', '\\"')
    return f'{field}:"{escaped}"'


def normalize_query(query: str) -> str:
    """Stable canonical form for cache keys (lowercase, trimmed)."""
    return query.strip().lower()


def cache_key(query: str, params: dict[str, object]) -> str:
    payload = json.dumps(
        {"q": normalize_query(query), "p": params}, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/services/test_query_builder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/query_builder.py tests/services/test_query_builder.py
git commit -m "feat: query builder with field whitelist and cache key"
```

---

## Task 7: DeHashed API client

**Files:**
- Create: `src/schemas/__init__.py`, `src/schemas/dehashed.py`, `src/repositories/__init__.py`, `src/repositories/external/__init__.py`, `src/repositories/external/dehashed.py`
- Test: `tests/repositories/test_dehashed_client.py`

**Interfaces:**
- Consumes: `Settings.dehashed_api_key`, `Settings.dehashed_base_url`, domain exceptions.
- Produces: pydantic `RawEntry` and `SearchResponse(balance: int, total: int, took: str | None, entries: list[RawEntry])`. `class DehashedClient(api_key: str, base_url: str, client: httpx.AsyncClient)` with `async def search(query: str, page: int = 1, size: int = 100, wildcard: bool = False, regex: bool = False) -> SearchResponse`.

- [ ] **Step 1: Implement `src/schemas/dehashed.py`**

```python
from pydantic import BaseModel, Field


class RawEntry(BaseModel):
    """One record as returned by DeHashed. Unknown fields ignored."""

    id: str | None = None
    email: str | None = None
    username: str | None = None
    password: str | None = None
    hashed_password: str | None = None
    name: str | None = None
    ip_address: str | None = None
    phone: str | None = None
    address: str | None = None
    database_name: str | None = None

    model_config = {"extra": "allow"}


class SearchResponse(BaseModel):
    balance: int = 0
    total: int = 0
    took: str | None = None
    entries: list[RawEntry] = Field(default_factory=list)
```

- [ ] **Step 2: Write the failing client test**

`tests/repositories/test_dehashed_client.py`:
```python
import httpx
import pytest
import respx

from src.core.exceptions import (
    DehashedAuthError,
    DehashedRateLimitError,
)
from src.repositories.external.dehashed import DehashedClient

BASE = "https://api.dehashed.com/v2"


@pytest.mark.asyncio
@respx.mock
async def test_search_parses_response():
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance": 500,
                "total": 1,
                "took": "5ms",
                "entries": [{"email": "a@b.com", "password": "pw", "database_name": "X"}],
            },
        )
    )
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc)
        resp = await client.search('email:"a@b.com"')
    assert resp.balance == 500
    assert resp.entries[0].email == "a@b.com"


@pytest.mark.asyncio
@respx.mock
async def test_401_raises_auth_error():
    respx.post(f"{BASE}/search").mock(return_value=httpx.Response(401))
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc)
        with pytest.raises(DehashedAuthError):
            await client.search("email:x")


@pytest.mark.asyncio
@respx.mock
async def test_429_retries_then_raises():
    route = respx.post(f"{BASE}/search").mock(return_value=httpx.Response(429))
    async with httpx.AsyncClient() as hc:
        client = DehashedClient("key", BASE, hc, max_retries=2, backoff_base=0)
        with pytest.raises(DehashedRateLimitError):
            await client.search("email:x")
    assert route.call_count == 3  # initial + 2 retries
```

- [ ] **Step 3: Run test to verify it fails**

Run: `poetry run pytest tests/repositories/test_dehashed_client.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement `src/repositories/external/dehashed.py`**

```python
import asyncio

import httpx

from src.core.exceptions import (
    DehashedAPIError,
    DehashedAuthError,
    DehashedRateLimitError,
)
from src.schemas.dehashed import SearchResponse

_AUTH_HEADER = "Dehashed-Api-Key"


class DehashedClient:
    """Async wrapper over the DeHashed v2 search API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        client: httpx.AsyncClient,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def search(
        self,
        query: str,
        page: int = 1,
        size: int = 100,
        wildcard: bool = False,
        regex: bool = False,
    ) -> SearchResponse:
        body = {
            "query": query,
            "page": page,
            "size": size,
            "wildcard": wildcard,
            "regex": regex,
        }
        headers = {_AUTH_HEADER: self._api_key, "Content-Type": "application/json"}
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            resp = await self._client.post(
                f"{self._base_url}/search", json=body, headers=headers
            )
            if resp.status_code == 200:
                return SearchResponse.model_validate(resp.json())
            if resp.status_code in (401, 403):
                raise DehashedAuthError("DeHashed authentication failed")
            if resp.status_code == 429:
                last_exc = DehashedRateLimitError("rate limited")
                if attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_base * (2**attempt))
                    continue
                raise last_exc
            raise DehashedAPIError(
                f"DeHashed returned {resp.status_code}"
            )
        assert last_exc is not None
        raise last_exc
```

- [ ] **Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/repositories/test_dehashed_client.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/schemas/ src/repositories/ tests/repositories/test_dehashed_client.py
git commit -m "feat: async DeHashed v2 client with retries and typed responses"
```

---

## Task 8: Repositories (investigations, searches, results)

**Files:**
- Create: `src/repositories/investigations.py`, `src/repositories/searches.py`
- Test: `tests/repositories/test_repositories.py`

**Interfaces:**
- Consumes: ORM models, `AsyncSession`.
- Produces:
  - `InvestigationRepository(session)`: `create(name, notes=None) -> Investigation`, `get(id) -> Investigation | None`, `list_all() -> list[Investigation]`, `add_target(investigation_id, label, entity_type="person") -> Target`, `add_selector(target_id, field_type, value) -> Selector`, `get_target(id) -> Target | None`.
  - `SearchRepository(session)`: `find_by_cache_key(cache_key) -> Search | None`, `create(target_id, query, params, cache_key, cost, balance_after, took) -> Search`, `add_records(search_id, target_id, entries) -> list[ResultRecord]`, `records_for_target(target_id) -> list[ResultRecord]`, `write_audit(action, query, cost) -> None`.

- [ ] **Step 1: Write the failing repository test**

`tests/repositories/test_repositories.py`:
```python
import pytest

from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import RawEntry


@pytest.mark.asyncio
async def test_investigation_target_selector_flow(db_session):
    repo = InvestigationRepository(db_session)
    inv = await repo.create("Op One", notes="n")
    target = await repo.add_target(inv.id, "jane")
    sel = await repo.add_selector(target.id, "email", "jane@x.com")
    assert sel.id is not None
    assert (await repo.get(inv.id)).name == "Op One"


@pytest.mark.asyncio
async def test_search_cache_lookup_and_records(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op Two")
    target = await inv_repo.add_target(inv.id, "jane")
    s_repo = SearchRepository(db_session)
    assert await s_repo.find_by_cache_key("missing") is None
    search = await s_repo.create(
        target.id, "email:x", "{}", "ck1", cost=1, balance_after=99, took="5ms"
    )
    assert (await s_repo.find_by_cache_key("ck1")).id == search.id
    recs = await s_repo.add_records(
        search.id, target.id, [RawEntry(email="a@b.com", password="pw", database_name="X")]
    )
    assert recs[0].password == "pw"
    assert len(await s_repo.records_for_target(target.id)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/repositories/test_repositories.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/repositories/investigations.py`**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Investigation, Selector, Target


class InvestigationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str, notes: str | None = None) -> Investigation:
        inv = Investigation(name=name, notes=notes)
        self._session.add(inv)
        await self._session.flush()
        return inv

    async def get(self, investigation_id: int) -> Investigation | None:
        return await self._session.get(Investigation, investigation_id)

    async def list_all(self) -> list[Investigation]:
        result = await self._session.execute(
            select(Investigation).order_by(Investigation.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_target(
        self, investigation_id: int, label: str, entity_type: str = "person"
    ) -> Target:
        target = Target(
            investigation_id=investigation_id, label=label, entity_type=entity_type
        )
        self._session.add(target)
        await self._session.flush()
        return target

    async def get_target(self, target_id: int) -> Target | None:
        return await self._session.get(Target, target_id)

    async def add_selector(
        self, target_id: int, field_type: str, value: str
    ) -> Selector:
        selector = Selector(target_id=target_id, field_type=field_type, value=value)
        self._session.add(selector)
        await self._session.flush()
        return selector
```

- [ ] **Step 4: Implement `src/repositories/searches.py`**

```python
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import AuditLog, ResultRecord, Search
from src.schemas.dehashed import RawEntry


class SearchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_cache_key(self, cache_key: str) -> Search | None:
        result = await self._session.execute(
            select(Search).where(Search.cache_key == cache_key).limit(1)
        )
        return result.scalars().first()

    async def create(
        self,
        target_id: int,
        query: str,
        params: str,
        cache_key: str,
        cost: int,
        balance_after: int,
        took: str | None,
    ) -> Search:
        search = Search(
            target_id=target_id,
            query=query,
            params=params,
            cache_key=cache_key,
            cost=cost,
            balance_after=balance_after,
            took=took,
        )
        self._session.add(search)
        await self._session.flush()
        return search

    async def add_records(
        self, search_id: int, target_id: int, entries: Sequence[RawEntry]
    ) -> list[ResultRecord]:
        records = [
            ResultRecord(
                search_id=search_id,
                target_id=target_id,
                raw_json=entry.model_dump_json(),
                email=entry.email,
                username=entry.username,
                password=entry.password,
                hashed_password=entry.hashed_password,
                name=entry.name,
                ip_address=entry.ip_address,
                phone=entry.phone,
                address=entry.address,
                database_name=entry.database_name,
            )
            for entry in entries
        ]
        self._session.add_all(records)
        await self._session.flush()
        return records

    async def records_for_target(self, target_id: int) -> list[ResultRecord]:
        result = await self._session.execute(
            select(ResultRecord).where(ResultRecord.target_id == target_id)
        )
        return list(result.scalars().all())

    async def write_audit(self, action: str, query: str | None, cost: int) -> None:
        self._session.add(AuditLog(action=action, query=query, cost=cost))
        await self._session.flush()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/repositories/test_repositories.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/repositories/investigations.py src/repositories/searches.py tests/repositories/test_repositories.py
git commit -m "feat: investigation and search repositories"
```

---

## Task 9: SearchService (cache + credit-guard + persist + audit)

**Files:**
- Create: `src/services/search_service.py`
- Test: `tests/services/test_search_service.py`

**Interfaces:**
- Consumes: `DehashedClient`, `SearchRepository`, `Settings.credit_guard_threshold`, `query_builder.cache_key`, `InsufficientCreditsError`.
- Produces: `class SearchService(repo: SearchRepository, client: DehashedClient, threshold: int)` with `async def run_search(target_id: int, query: str, page: int = 1, size: int = 100) -> Search`. Behavior: returns cached `Search` if `cache_key` already exists (no credits spent); otherwise pre-flight balance check raising `InsufficientCreditsError` when probe balance ≤ threshold; else calls client, persists search + records, writes audit.

- [ ] **Step 1: Write the failing test**

`tests/services/test_search_service.py`:
```python
import pytest

from src.core.exceptions import InsufficientCreditsError
from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import RawEntry, SearchResponse
from src.services.search_service import SearchService


class FakeClient:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls = 0

    async def search(self, query, page=1, size=100, wildcard=False, regex=False):
        self.calls += 1
        return self.response


@pytest.mark.asyncio
async def test_run_search_persists_and_audits(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    client = FakeClient(
        SearchResponse(balance=400, total=1, took="3ms", entries=[RawEntry(email="a@b.com")])
    )
    svc = SearchService(SearchRepository(db_session), client, threshold=100)
    search = await svc.run_search(target.id, 'email:"a@b.com"')
    assert search.balance_after == 400
    assert client.calls == 1


@pytest.mark.asyncio
async def test_duplicate_query_uses_cache_no_spend(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    client = FakeClient(SearchResponse(balance=400, total=0, entries=[]))
    svc = SearchService(SearchRepository(db_session), client, threshold=100)
    await svc.run_search(target.id, 'email:"a@b.com"')
    await svc.run_search(target.id, 'email:"a@b.com"')
    assert client.calls == 1  # second call served from cache


@pytest.mark.asyncio
async def test_credit_guard_blocks_below_threshold(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    client = FakeClient(SearchResponse(balance=50, total=0, entries=[]))
    svc = SearchService(SearchRepository(db_session), client, threshold=100)
    with pytest.raises(InsufficientCreditsError):
        await svc.run_search(target.id, 'email:"a@b.com"')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/services/test_search_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/services/search_service.py`**

```python
import json
from typing import Protocol

from src.core.exceptions import InsufficientCreditsError
from src.models import Search
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import SearchResponse
from src.services.query_builder import cache_key


class _Client(Protocol):
    async def search(
        self, query: str, page: int = 1, size: int = 100,
        wildcard: bool = False, regex: bool = False,
    ) -> SearchResponse: ...


class SearchService:
    """Runs DeHashed searches with caching, credit-guard, persistence, audit."""

    def __init__(
        self, repo: SearchRepository, client: _Client, threshold: int
    ) -> None:
        self._repo = repo
        self._client = client
        self._threshold = threshold

    async def run_search(
        self, target_id: int, query: str, page: int = 1, size: int = 100
    ) -> Search:
        params = {"page": page, "size": size}
        key = cache_key(query, params)

        cached = await self._repo.find_by_cache_key(key)
        if cached is not None:
            return cached  # identical query already run; spend nothing

        response = await self._client.search(query, page=page, size=size)
        if response.balance <= self._threshold:
            # Pre-flight guard: refuse to keep spending near empty.
            raise InsufficientCreditsError(response.balance, self._threshold)

        search = await self._repo.create(
            target_id=target_id,
            query=query,
            params=json.dumps(params, sort_keys=True),
            cache_key=key,
            cost=max(response.total, 1),
            balance_after=response.balance,
            took=response.took,
        )
        await self._repo.add_records(search.id, target_id, response.entries)
        await self._repo.write_audit("search", query, search.cost)
        return search
```

> **Note:** the credit-guard checks the balance the API *returns*. The DeHashed call has already happened, so this guards future spend, not the current call. Document this in the UI ("you have N credits left"). A true pre-spend block would require a separate balance endpoint; if DeHashed exposes one, add a `get_balance()` to `DehashedClient` and check it before `search()`. Tracked as a follow-up.

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/services/test_search_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/search_service.py tests/services/test_search_service.py
git commit -m "feat: SearchService with cache, credit-guard, audit"
```

---

## Task 10: CorrelationService (dedup, hash-type ID, reuse, breach mapping)

**Files:**
- Create: `src/schemas/domain.py`, `src/services/correlation_service.py`
- Test: `tests/services/test_correlation_service.py`

**Interfaces:**
- Consumes: `ResultRecord`, `SearchRepository.records_for_target`.
- Produces:
  - `identify_hash_type(value: str) -> str` (returns `"MD5"`, `"SHA-1"`, `"SHA-256"`, `"bcrypt"`, or `"unknown"`).
  - pydantic `TargetProfile(emails: list[str], usernames: list[str], passwords: list[str], ip_addresses: list[str], reused_passwords: list[str], breach_sources: dict[str, int], hash_types: dict[str, str])`.
  - `class CorrelationService(repo: SearchRepository)` with `async def build_profile(target_id: int) -> TargetProfile`.

- [ ] **Step 1: Write the failing test**

`tests/services/test_correlation_service.py`:
```python
import pytest

from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.schemas.dehashed import RawEntry
from src.services.correlation_service import CorrelationService, identify_hash_type


@pytest.mark.parametrize(
    "value,expected",
    [
        ("5f4dcc3b5aa765d61d8327deb882cf99", "MD5"),
        ("aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d", "SHA-1"),
        ("$2b$12$" + "a" * 53, "bcrypt"),
        ("notahash", "unknown"),
    ],
)
def test_identify_hash_type(value, expected):
    assert identify_hash_type(value) == expected


@pytest.mark.asyncio
async def test_build_profile_dedups_and_maps(db_session):
    inv_repo = InvestigationRepository(db_session)
    inv = await inv_repo.create("Op")
    target = await inv_repo.add_target(inv.id, "jane")
    s_repo = SearchRepository(db_session)
    s = await s_repo.create(target.id, "q", "{}", "ck", 1, 99, "1ms")
    await s_repo.add_records(
        s.id, target.id,
        [
            RawEntry(email="a@b.com", password="reuse", database_name="LeakA"),
            RawEntry(email="a@b.com", password="reuse", database_name="LeakB"),
            RawEntry(username="jane", password="other", database_name="LeakA"),
        ],
    )
    profile = await CorrelationService(s_repo).build_profile(target.id)
    assert profile.emails == ["a@b.com"]  # deduped
    assert "reuse" in profile.reused_passwords  # appears in 2 breaches
    assert profile.breach_sources == {"LeakA": 2, "LeakB": 1}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/services/test_correlation_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/schemas/domain.py`**

```python
from pydantic import BaseModel, Field


class TargetProfile(BaseModel):
    emails: list[str] = Field(default_factory=list)
    usernames: list[str] = Field(default_factory=list)
    passwords: list[str] = Field(default_factory=list)
    ip_addresses: list[str] = Field(default_factory=list)
    reused_passwords: list[str] = Field(default_factory=list)
    breach_sources: dict[str, int] = Field(default_factory=dict)
    hash_types: dict[str, str] = Field(default_factory=dict)


class PivotSuggestion(BaseModel):
    field_type: str
    value: str
    query: str
```

- [ ] **Step 4: Implement `src/services/correlation_service.py`**

```python
import re
from collections import Counter

from src.repositories.searches import SearchRepository
from src.schemas.domain import TargetProfile

_MD5 = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
_SHA1 = re.compile(r"^[a-f0-9]{40}$", re.IGNORECASE)
_SHA256 = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)
_BCRYPT = re.compile(r"^\$2[aby]\$\d{2}\$.{53}$")


def identify_hash_type(value: str) -> str:
    if _BCRYPT.match(value):
        return "bcrypt"
    if _MD5.match(value):
        return "MD5"
    if _SHA1.match(value):
        return "SHA-1"
    if _SHA256.match(value):
        return "SHA-256"
    return "unknown"


def _dedup_preserve(values: list[str | None]) -> list[str]:
    seen: dict[str, None] = {}
    for v in values:
        if v:
            seen.setdefault(v, None)
    return list(seen)


class CorrelationService:
    def __init__(self, repo: SearchRepository) -> None:
        self._repo = repo

    async def build_profile(self, target_id: int) -> TargetProfile:
        records = await self._repo.records_for_target(target_id)

        emails = _dedup_preserve([r.email for r in records])
        usernames = _dedup_preserve([r.username for r in records])
        passwords = _dedup_preserve([r.password for r in records])
        ips = _dedup_preserve([r.ip_address for r in records])

        # Reuse = same plaintext password across >1 distinct breach source.
        pw_breaches: dict[str, set[str]] = {}
        for r in records:
            if r.password and r.database_name:
                pw_breaches.setdefault(r.password, set()).add(r.database_name)
        reused = [pw for pw, srcs in pw_breaches.items() if len(srcs) > 1]

        breach_sources = dict(
            Counter(r.database_name for r in records if r.database_name)
        )

        hash_types = {
            r.hashed_password: identify_hash_type(r.hashed_password)
            for r in records
            if r.hashed_password
        }

        return TargetProfile(
            emails=emails,
            usernames=usernames,
            passwords=passwords,
            ip_addresses=ips,
            reused_passwords=reused,
            breach_sources=breach_sources,
            hash_types=hash_types,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/services/test_correlation_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/schemas/domain.py src/services/correlation_service.py tests/services/test_correlation_service.py
git commit -m "feat: correlation service with dedup, hash-id, reuse, breach map"
```

---

## Task 11: PivotService

**Files:**
- Create: `src/services/pivot_service.py`
- Test: `tests/services/test_pivot_service.py`

**Interfaces:**
- Consumes: `query_builder.build_query`, `ALLOWED_FIELDS`, `PivotSuggestion`.
- Produces: `suggest_pivot(field_type: str, value: str) -> PivotSuggestion` (raises `ValueError` on non-pivotable field).

- [ ] **Step 1: Write the failing test**

`tests/services/test_pivot_service.py`:
```python
import pytest

from src.services.pivot_service import suggest_pivot


def test_pivot_on_email_builds_query():
    s = suggest_pivot("email", "a@b.com")
    assert s.field_type == "email"
    assert s.query == 'email:"a@b.com"'


def test_pivot_on_unknown_field_raises():
    with pytest.raises(ValueError):
        suggest_pivot("ssn", "123")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/services/test_pivot_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/services/pivot_service.py`**

```python
from src.schemas.domain import PivotSuggestion
from src.services.query_builder import build_query


def suggest_pivot(field_type: str, value: str) -> PivotSuggestion:
    """Turn a result field into a ready-to-run seeded search.

    build_query raises ValueError for non-whitelisted (non-pivotable) fields.
    """
    query = build_query(field_type, value)
    return PivotSuggestion(field_type=field_type, value=value, query=query)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/services/test_pivot_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/services/pivot_service.py tests/services/test_pivot_service.py
git commit -m "feat: pivot service"
```

---

## Task 12: ReportService (CSV / JSON / PDF)

**Files:**
- Create: `src/services/report_service.py`, `src/templates/report.html`
- Test: `tests/services/test_report_service.py`

**Interfaces:**
- Consumes: `ResultRecord`, `TargetProfile`.
- Produces: `records_to_csv(records: list[ResultRecord]) -> str`, `records_to_json(records: list[ResultRecord]) -> str`, `profile_to_pdf(investigation_name: str, target_label: str, profile: TargetProfile) -> bytes`.

- [ ] **Step 1: Write the failing test**

`tests/services/test_report_service.py`:
```python
from src.schemas.domain import TargetProfile
from src.services.report_service import (
    profile_to_pdf,
    records_to_csv,
    records_to_json,
)


class FakeRecord:
    email = "a@b.com"
    username = "jane"
    password = "pw"
    hashed_password = None
    ip_address = "1.2.3.4"
    database_name = "LeakA"


def test_csv_has_header_and_row():
    csv = records_to_csv([FakeRecord()])
    assert "email" in csv.splitlines()[0]
    assert "a@b.com" in csv


def test_json_is_list():
    import json
    data = json.loads(records_to_json([FakeRecord()]))
    assert data[0]["email"] == "a@b.com"


def test_pdf_starts_with_magic_bytes():
    profile = TargetProfile(emails=["a@b.com"], breach_sources={"LeakA": 1})
    pdf = profile_to_pdf("Op", "jane", profile)
    assert pdf[:4] == b"%PDF"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/services/test_report_service.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/templates/report.html`**

```html
<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { font-family: sans-serif; } h1 { font-size: 18px; }
  .sec { margin-bottom: 16px; } code { background:#eee; padding:1px 3px; }
</style></head><body>
  <h1>Investigation: {{ investigation_name }} — Target: {{ target_label }}</h1>
  <div class="sec"><strong>Emails:</strong> {{ profile.emails | join(", ") }}</div>
  <div class="sec"><strong>Usernames:</strong> {{ profile.usernames | join(", ") }}</div>
  <div class="sec"><strong>Reused passwords:</strong> {{ profile.reused_passwords | length }}</div>
  <div class="sec"><strong>Breach sources:</strong>
    <ul>{% for src, n in profile.breach_sources.items() %}<li>{{ src }}: {{ n }}</li>{% endfor %}</ul>
  </div>
</body></html>
```

- [ ] **Step 4: Implement `src/services/report_service.py`**

```python
import csv
import io
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from src.schemas.domain import TargetProfile

_CSV_FIELDS = [
    "email", "username", "password", "hashed_password", "ip_address", "database_name",
]
_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES)),
    autoescape=select_autoescape(["html"]),
)


def records_to_csv(records: list[Any]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for r in records:
        writer.writerow({f: getattr(r, f, None) for f in _CSV_FIELDS})
    return buf.getvalue()


def records_to_json(records: list[Any]) -> str:
    return json.dumps(
        [{f: getattr(r, f, None) for f in _CSV_FIELDS} for r in records], indent=2
    )


def profile_to_pdf(
    investigation_name: str, target_label: str, profile: TargetProfile
) -> bytes:
    html = _env.get_template("report.html").render(
        investigation_name=investigation_name,
        target_label=target_label,
        profile=profile,
    )
    return HTML(string=html).write_pdf()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/services/test_report_service.py -v`
Expected: PASS (WeasyPrint must be installed with its system libs; on Windows use the WeasyPrint install docs or run reports inside the docker image)

- [ ] **Step 6: Commit**

```bash
git add src/services/report_service.py src/templates/report.html tests/services/test_report_service.py
git commit -m "feat: report service (csv/json/pdf)"
```

---

## Task 13: JSON API — investigations, searches, pivot graph

**Files:**
- Create: `src/api/__init__.py`, `src/api/v1/__init__.py`, `src/api/v1/investigations.py`, `src/api/v1/searches.py`
- Modify: `src/main.py` (mount routers, build per-request services)
- Test: `tests/api/test_v1.py`

**Interfaces:**
- Consumes: repositories, `SearchService`, `CorrelationService`, `suggest_pivot`, `DehashedClient`, `get_session`.
- Produces routes:
  - `POST /v1/investigations` → `{id, name}`; `GET /v1/investigations`; `POST /v1/investigations/{id}/targets`.
  - `POST /v1/targets/{target_id}/searches` body `{field, value}` → runs search, returns `{search_id, total, balance_after}`; maps `InsufficientCreditsError`→402, `DehashedAuthError`→502.
  - `GET /v1/targets/{target_id}/profile` → `TargetProfile`.
  - `GET /v1/targets/{target_id}/graph` → Cytoscape elements `{nodes, edges}` built from the profile (target node + one node per email/username/ip, edges target→selector).

- [ ] **Step 1: Write the failing API test**

`tests/api/test_v1.py`:
```python
import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.main import create_app

BASE = "https://api.dehashed.com/v2"


@pytest.fixture
def client(monkeypatch):
    import base64, os
    monkeypatch.setenv("DEHASHED_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint")
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("DEHASHED_BASE_URL", BASE)
    from src.core.config import get_settings
    get_settings.cache_clear()
    return TestClient(create_app())


@respx.mock
def test_full_investigation_search_flow(client):
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(
            200,
            json={"balance": 500, "total": 1, "took": "2ms",
                  "entries": [{"email": "a@b.com", "database_name": "LeakA"}]},
        )
    )
    inv = client.post("/v1/investigations", json={"name": "Op"}).json()
    target = client.post(f"/v1/investigations/{inv['id']}/targets", json={"label": "jane"}).json()
    run = client.post(f"/v1/targets/{target['id']}/searches", json={"field": "email", "value": "a@b.com"})
    assert run.status_code == 200
    assert run.json()["balance_after"] == 500
    profile = client.get(f"/v1/targets/{target['id']}/profile").json()
    assert profile["emails"] == ["a@b.com"]
    graph = client.get(f"/v1/targets/{target['id']}/graph").json()
    assert any(n["data"]["id"] == "email:a@b.com" for n in graph["nodes"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/api/test_v1.py -v`
Expected: FAIL (routes 404 / app has no routers)

- [ ] **Step 3: Implement `src/api/v1/investigations.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_session
from src.repositories.investigations import InvestigationRepository

router = APIRouter(prefix="/v1", tags=["investigations"])


class InvestigationIn(BaseModel):
    name: str
    notes: str | None = None


class TargetIn(BaseModel):
    label: str
    entity_type: str = "person"


@router.post("/investigations")
async def create_investigation(
    body: InvestigationIn, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    repo = InvestigationRepository(session)
    inv = await repo.create(body.name, body.notes)
    await session.commit()
    return {"id": inv.id, "name": inv.name}


@router.get("/investigations")
async def list_investigations(
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, object]]:
    repo = InvestigationRepository(session)
    return [{"id": i.id, "name": i.name, "status": i.status} for i in await repo.list_all()]


@router.post("/investigations/{investigation_id}/targets")
async def add_target(
    investigation_id: int, body: TargetIn, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    repo = InvestigationRepository(session)
    target = await repo.add_target(investigation_id, body.label, body.entity_type)
    await session.commit()
    return {"id": target.id, "label": target.label}
```

- [ ] **Step 4: Implement `src/api/v1/searches.py`**

```python
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db import get_session
from src.core.exceptions import DehashedAuthError, InsufficientCreditsError
from src.repositories.searches import SearchRepository
from src.repositories.external.dehashed import DehashedClient
from src.schemas.domain import TargetProfile
from src.services.correlation_service import CorrelationService
from src.services.query_builder import build_query
from src.services.search_service import SearchService

router = APIRouter(prefix="/v1", tags=["searches"])


class SearchIn(BaseModel):
    field: str
    value: str


@router.post("/targets/{target_id}/searches")
async def run_search(
    target_id: int, body: SearchIn, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    settings = get_settings()
    try:
        query = build_query(body.field, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    async with httpx.AsyncClient(timeout=30) as hc:
        client = DehashedClient(
            settings.dehashed_api_key.get_secret_value(),
            settings.dehashed_base_url,
            hc,
        )
        svc = SearchService(
            SearchRepository(session), client, settings.credit_guard_threshold
        )
        try:
            search = await svc.run_search(target_id, query)
        except InsufficientCreditsError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        except DehashedAuthError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    await session.commit()
    return {
        "search_id": search.id,
        "cost": search.cost,
        "balance_after": search.balance_after,
    }


@router.get("/targets/{target_id}/profile")
async def get_profile(
    target_id: int, session: AsyncSession = Depends(get_session)
) -> TargetProfile:
    return await CorrelationService(SearchRepository(session)).build_profile(target_id)


@router.get("/targets/{target_id}/graph")
async def get_graph(
    target_id: int, session: AsyncSession = Depends(get_session)
) -> dict[str, list[dict[str, object]]]:
    profile = await CorrelationService(SearchRepository(session)).build_profile(target_id)
    nodes: list[dict[str, object]] = [
        {"data": {"id": f"target:{target_id}", "label": "TARGET", "kind": "target"}}
    ]
    edges: list[dict[str, object]] = []
    for field, values in (("email", profile.emails), ("username", profile.usernames), ("ip_address", profile.ip_addresses)):
        for value in values:
            node_id = f"{field}:{value}"
            nodes.append({"data": {"id": node_id, "label": value, "kind": field}})
            edges.append({"data": {"source": f"target:{target_id}", "target": node_id}})
    return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 5: Mount routers in `src/main.py`**

Add inside `create_app()` before `return app`:
```python
    from src.api.v1 import investigations, searches

    app.include_router(investigations.router)
    app.include_router(searches.router)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `poetry run pytest tests/api/test_v1.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/api/ src/main.py tests/api/test_v1.py
git commit -m "feat: v1 JSON API for investigations, searches, profile, graph"
```

---

## Task 14: HTMX web UI + authorization gate

**Files:**
- Create: `src/api/web/__init__.py`, `src/api/web/pages.py`, `src/templates/base.html`, `src/templates/investigations.html`, `src/templates/target.html`, `src/templates/_results.html`, `src/templates/graph.html`, `src/templates/authorize.html`, `src/static/app.css`
- Download: `src/static/htmx.min.js`, `src/static/cytoscape.min.js`
- Modify: `src/main.py` (mount static + web router + auth-gate middleware)
- Test: `tests/api/test_web.py`

**Interfaces:**
- Consumes: repositories, services, `get_session`, Jinja templates.
- Produces routes: `GET /` (investigations list), `POST /ui/investigations` (HTMX create → row partial), `GET /ui/targets/{id}` (target detail page), `POST /ui/targets/{id}/search` (HTMX → `_results.html` partial), `GET /ui/targets/{id}/graph` (Cytoscape page), `GET /authorize` + `POST /authorize` (sets a signed cookie `osint_authorized=1`). Middleware redirects to `/authorize` until the cookie is present.

- [ ] **Step 1: Write the failing web test**

`tests/api/test_web.py`:
```python
import base64
import os

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEHASHED_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint")
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    from src.core.config import get_settings
    get_settings.cache_clear()
    return TestClient(create_app())


def test_unauthorized_redirects_to_gate(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"].endswith("/authorize")


def test_authorize_then_home_renders(client):
    client.post("/authorize", data={"ack": "yes"})
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Investigations" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/api/test_web.py -v`
Expected: FAIL (no `/authorize`, no web router)

- [ ] **Step 3: Implement templates**

`src/templates/base.html`:
```html
<!doctype html>
<html><head>
  <meta charset="utf-8"><title>DeHashed OSINT</title>
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/htmx.min.js"></script>
</head><body>
  <header><strong>DeHashed OSINT Platform</strong> — authorized use only</header>
  <main>{% block content %}{% endblock %}</main>
</body></html>
```

`src/templates/authorize.html`:
```html
{% extends "base.html" %}{% block content %}
<h1>Authorization Required</h1>
<p>Confirm you are authorized to search for leaked data on these targets.
   All searches are logged.</p>
<form method="post" action="/authorize">
  <button name="ack" value="yes" type="submit">I am authorized — proceed</button>
</form>
{% endblock %}
```

`src/templates/investigations.html`:
```html
{% extends "base.html" %}{% block content %}
<h1>Investigations</h1>
<form hx-post="/ui/investigations" hx-target="#inv-list" hx-swap="afterbegin">
  <input name="name" placeholder="Investigation name" required>
  <button type="submit">Create</button>
</form>
<ul id="inv-list">
  {% for inv in investigations %}<li><a href="/ui/targets/{{ inv.id }}">{{ inv.name }}</a></li>{% endfor %}
</ul>
{% endblock %}
```

`src/templates/target.html`:
```html
{% extends "base.html" %}{% block content %}
<h1>Target: {{ target.label }}</h1>
<form hx-post="/ui/targets/{{ target.id }}/search" hx-target="#results">
  <select name="field">
    {% for f in fields %}<option value="{{ f }}">{{ f }}</option>{% endfor %}
  </select>
  <input name="value" placeholder="value" required>
  <button type="submit">Search</button>
</form>
<a href="/ui/targets/{{ target.id }}/graph">Pivot graph</a>
<div id="results">{% include "_results.html" %}</div>
{% endblock %}
```

`src/templates/_results.html`:
```html
<table>
  <tr><th>email</th><th>username</th><th>password</th><th>breach</th><th></th></tr>
  {% for r in records %}
  <tr>
    <td>{{ r.email or "" }}</td><td>{{ r.username or "" }}</td>
    <td>{{ r.password or "" }}</td><td>{{ r.database_name or "" }}</td>
    <td>{% if r.email %}<button
        hx-post="/ui/targets/{{ target_id }}/search"
        hx-vals='{"field":"email","value":"{{ r.email }}"}'
        hx-target="#results">pivot</button>{% endif %}</td>
  </tr>
  {% endfor %}
</table>
{% if profile %}<p>Reused passwords: {{ profile.reused_passwords | length }} ·
  Breaches: {{ profile.breach_sources | length }}</p>{% endif %}
```

`src/templates/graph.html`:
```html
{% extends "base.html" %}{% block content %}
<h1>Pivot graph: {{ target.label }}</h1>
<div id="cy" style="width:100%;height:600px;border:1px solid #ccc"></div>
<script src="/static/cytoscape.min.js"></script>
<script>
  fetch("/v1/targets/{{ target.id }}/graph").then(r => r.json()).then(g => {
    cytoscape({ container: document.getElementById("cy"),
      elements: g.nodes.concat(g.edges),
      style: [{ selector: "node", style: { label: "data(label)" } }] });
  });
</script>
{% endblock %}
```

- [ ] **Step 4: Implement `src/api/web/pages.py`**

```python
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db import get_session
from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.services.correlation_service import CorrelationService
from src.services.query_builder import ALLOWED_FIELDS
from src.services.search_service import SearchService
from src.repositories.external.dehashed import DehashedClient
import httpx

router = APIRouter()
_templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent.parent / "templates")
)


@router.get("/authorize", response_class=HTMLResponse)
async def authorize_form(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(request, "authorize.html")


@router.post("/authorize")
async def authorize_submit(ack: str = Form(...)) -> RedirectResponse:
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("osint_authorized", "1", httponly=True, samesite="strict")
    return resp


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    investigations = await InvestigationRepository(session).list_all()
    return _templates.TemplateResponse(
        request, "investigations.html", {"investigations": investigations}
    )


@router.post("/ui/investigations", response_class=HTMLResponse)
async def create_investigation_ui(
    request: Request, name: str = Form(...), session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    inv = await InvestigationRepository(session).create(name)
    await session.commit()
    return HTMLResponse(f'<li><a href="/ui/targets/{inv.id}">{inv.name}</a></li>')


@router.get("/ui/targets/{target_id}", response_class=HTMLResponse)
async def target_page(
    request: Request, target_id: int, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    repo = InvestigationRepository(session)
    target = await repo.get_target(target_id)
    records = await SearchRepository(session).records_for_target(target_id)
    return _templates.TemplateResponse(
        request,
        "target.html",
        {"target": target, "records": records, "fields": sorted(ALLOWED_FIELDS),
         "target_id": target_id, "profile": None},
    )


@router.post("/ui/targets/{target_id}/search", response_class=HTMLResponse)
async def search_ui(
    request: Request,
    target_id: int,
    field: str = Form(...),
    value: str = Form(...),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    from src.services.query_builder import build_query

    settings = get_settings()
    query = build_query(field, value)
    async with httpx.AsyncClient(timeout=30) as hc:
        client = DehashedClient(
            settings.dehashed_api_key.get_secret_value(), settings.dehashed_base_url, hc
        )
        svc = SearchService(SearchRepository(session), client, settings.credit_guard_threshold)
        await svc.run_search(target_id, query)
    await session.commit()
    s_repo = SearchRepository(session)
    records = await s_repo.records_for_target(target_id)
    profile = await CorrelationService(s_repo).build_profile(target_id)
    return _templates.TemplateResponse(
        request, "_results.html",
        {"records": records, "target_id": target_id, "profile": profile},
    )


@router.get("/ui/targets/{target_id}/graph", response_class=HTMLResponse)
async def graph_page(
    request: Request, target_id: int, session: AsyncSession = Depends(get_session)
) -> HTMLResponse:
    target = await InvestigationRepository(session).get_target(target_id)
    return _templates.TemplateResponse(request, "graph.html", {"target": target})
```

- [ ] **Step 5: Add auth-gate middleware + static mount in `src/main.py`**

Add inside `create_app()` (after routers, before `return app`):
```python
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import RedirectResponse

    from src.api.web import pages

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(pages.router)

    _EXEMPT = ("/authorize", "/static", "/healthz", "/v1")

    async def _gate(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path.startswith(_EXEMPT) or request.cookies.get("osint_authorized"):
            return await call_next(request)
        return RedirectResponse("/authorize", status_code=307)

    app.add_middleware(BaseHTTPMiddleware, dispatch=_gate)
```

- [ ] **Step 6: Fetch vendored JS assets**

Run:
```bash
curl -L https://unpkg.com/htmx.org/dist/htmx.min.js -o src/static/htmx.min.js
curl -L https://unpkg.com/cytoscape/dist/cytoscape.min.js -o src/static/cytoscape.min.js
printf 'body{font-family:sans-serif;margin:2rem;} table{border-collapse:collapse;} td,th{border:1px solid #ccc;padding:4px;}' > src/static/app.css
```

- [ ] **Step 7: Run test to verify it passes**

Run: `poetry run pytest tests/api/test_web.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/api/web/ src/templates/ src/static/ src/main.py tests/api/test_web.py
git commit -m "feat: HTMX web UI, pivot graph, authorization gate"
```

---

## Task 15: Export endpoints + run docs

**Files:**
- Create: `src/api/v1/exports.py`, `README.md`
- Modify: `src/main.py` (mount exports router)
- Test: `tests/api/test_exports.py`

**Interfaces:**
- Consumes: `SearchRepository.records_for_target`, `InvestigationRepository.get_target`, `report_service`, `CorrelationService`.
- Produces: `GET /v1/targets/{id}/export.csv`, `GET /v1/targets/{id}/export.json`, `GET /v1/targets/{id}/report.pdf` (correct `Content-Type` + `Content-Disposition`).

- [ ] **Step 1: Write the failing test**

`tests/api/test_exports.py`:
```python
import base64
import os

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src.main import create_app

BASE = "https://api.dehashed.com/v2"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEHASHED_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://osint:osint@localhost:5432/osint")
    monkeypatch.setenv("ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("DEHASHED_BASE_URL", BASE)
    from src.core.config import get_settings
    get_settings.cache_clear()
    return TestClient(create_app())


@respx.mock
def test_csv_export(client):
    respx.post(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json={"balance": 500, "total": 1,
            "entries": [{"email": "a@b.com", "database_name": "LeakA"}]})
    )
    inv = client.post("/v1/investigations", json={"name": "Op"}).json()
    t = client.post(f"/v1/investigations/{inv['id']}/targets", json={"label": "jane"}).json()
    client.post(f"/v1/targets/{t['id']}/searches", json={"field": "email", "value": "a@b.com"})
    resp = client.get(f"/v1/targets/{t['id']}/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "a@b.com" in resp.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/api/test_exports.py -v`
Expected: FAIL (route 404)

- [ ] **Step 3: Implement `src/api/v1/exports.py`**

```python
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_session
from src.repositories.investigations import InvestigationRepository
from src.repositories.searches import SearchRepository
from src.services.correlation_service import CorrelationService
from src.services.report_service import (
    profile_to_pdf,
    records_to_csv,
    records_to_json,
)

router = APIRouter(prefix="/v1", tags=["exports"])


@router.get("/targets/{target_id}/export.csv")
async def export_csv(
    target_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    records = await SearchRepository(session).records_for_target(target_id)
    return Response(
        records_to_csv(records),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="target_{target_id}.csv"'},
    )


@router.get("/targets/{target_id}/export.json")
async def export_json(
    target_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    records = await SearchRepository(session).records_for_target(target_id)
    return Response(records_to_json(records), media_type="application/json")


@router.get("/targets/{target_id}/report.pdf")
async def report_pdf(
    target_id: int, session: AsyncSession = Depends(get_session)
) -> Response:
    inv_repo = InvestigationRepository(session)
    s_repo = SearchRepository(session)
    target = await inv_repo.get_target(target_id)
    assert target is not None
    investigation = await inv_repo.get(target.investigation_id)
    profile = await CorrelationService(s_repo).build_profile(target_id)
    pdf = profile_to_pdf(investigation.name if investigation else "", target.label, profile)
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="target_{target_id}.pdf"'},
    )
```

- [ ] **Step 4: Mount exports router in `src/main.py`**

Add alongside the other `include_router` calls:
```python
    from src.api.v1 import exports

    app.include_router(exports.router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `poetry run pytest tests/api/test_exports.py -v`
Expected: PASS

- [ ] **Step 6: Write `README.md`**

Include: project purpose + authorization disclaimer, prerequisites (Python 3.11+, Docker, DeHashed API key), setup (`cp .env.example .env`, generate `ENCRYPTION_KEY`, `docker compose up -d postgres`, `poetry install`, `poetry run alembic upgrade head`), run (`poetry run uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000`), test (`poetry run pytest`), and the full quality gate (`black . && ruff check . && mypy && pytest`).

- [ ] **Step 7: Run the full suite + quality gate**

Run:
```bash
poetry run black --check . && poetry run ruff check . && poetry run mypy && poetry run pytest
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add src/api/v1/exports.py src/main.py README.md tests/api/test_exports.py
git commit -m "feat: csv/json/pdf export endpoints + run docs"
```

---

## Self-Review Notes

- **Spec coverage:** investigations/targets/selectors (Tasks 4, 8, 13, 14); DeHashed v2 client w/ retries + experimental wildcard/regex flags (Task 7); credit-guard + caching (Task 9); pivoting (Tasks 11, 13, 14); correlation/dedup + credential analysis + breach mapping (Task 10); app-layer AES-GCM encryption (Tasks 2, 4); audit log (Tasks 4, 8, 9); PII-redacting structlog (Task 1); authorization gate (Task 14); PDF/CSV/JSON export (Tasks 12, 15); Postgres + Alembic (Task 4); HTMX + Cytoscape UI (Task 14). All spec sections map to a task.
- **Credit-guard caveat:** the guard reads the post-call balance (documented in Task 9 Step 3 note); a true pre-spend guard needs a DeHashed balance endpoint — flagged as follow-up, matching the spec's "warn before spending" intent within the API's constraints.
- **Type consistency:** `cache_key`, `build_query`, `ALLOWED_FIELDS`, `TargetProfile`, `SearchResponse`, `RawEntry`, `DehashedClient.search`, `SearchService.run_search`, `CorrelationService.build_profile`, and repository method names are used identically across tasks.
- **Scope cuts honored:** no bundled hash cracking (only `identify_hash_type`); no materialized correlation table (computed in `build_profile`); no auth UI (only the gate + `owner_id` plumbing).
