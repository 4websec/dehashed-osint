"""Shared pytest fixtures for the test suite.

Task 4 provides the foundational seam here: Settings construction with a live
generated key, EncryptedString cipher configuration, and an async db_session
fixture that rolls back after each test to keep the DB clean.

Task 5 will extend this file rather than recreate it.
"""

import asyncio
import base64
import os
from collections.abc import AsyncIterator

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings
from src.core.crypto import EncryptedString, FieldCipher
from src.core.db import Base

# Tests run against a SEPARATE database (default: osint_test), never the app's
# `osint` database — the per-test TRUNCATE below would otherwise destroy real
# investigation data on every `pytest` run. Override with TEST_DATABASE_URL.
_TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://osint:osint@localhost:5432/osint_test",
)

# All tables, child-first, for a deterministic TRUNCATE before each test.
_ALL_TABLES = (
    "audit_log",
    "result_records",
    "searches",
    "selectors",
    "targets",
    "investigations",
    "users",
)


async def _create_test_database_if_missing() -> None:
    """Create the test database if it doesn't exist (CREATE DATABASE can't run
    inside a transaction, so connect to the `postgres` maintenance DB directly
    via asyncpg in autocommit)."""
    url = make_url(_TEST_DATABASE_URL)
    admin = await asyncpg.connect(
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database="postgres",
    )
    try:
        exists = await admin.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", url.database
        )
        if not exists:
            await admin.execute(f'CREATE DATABASE "{url.database}"')
    finally:
        await admin.close()


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_database() -> None:
    """Guarantee the dedicated test database exists before any engine connects."""
    asyncio.run(_create_test_database_if_missing())


@pytest.fixture(scope="session")
def test_settings(_ensure_test_database: None) -> Settings:
    """Build Settings directly with a generated key; no real .env required."""
    key = base64.b64encode(os.urandom(32)).decode()
    return Settings(
        dehashed_api_key="test-placeholder",  # type: ignore[arg-type]
        database_url=_TEST_DATABASE_URL,
        encryption_key=key,  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True, scope="session")
def configure_cipher(test_settings: Settings) -> None:
    """Inject FieldCipher into EncryptedString once per session.

    EncryptedString.configure() is a class-level call; it only needs to run
    once, but must run before any DB I/O that touches encrypted columns.
    """
    EncryptedString.configure(
        FieldCipher(test_settings.encryption_key.get_secret_value())
    )


@pytest_asyncio.fixture(autouse=True)
async def _clean_db(test_settings: Settings) -> AsyncIterator[None]:
    """Reset the database to a clean, seeded state before EVERY test.

    Integration tests drive the app through TestClient, whose routes use the
    app's own sessions and COMMIT to Postgres. Those committed rows are not
    rolled back by ``db_session`` and would otherwise leak across tests and
    across runs (the docker volume persists), causing false cache-key hits in
    SearchService tests. TRUNCATE ... RESTART IDENTITY CASCADE before each test
    guarantees isolation regardless of test order; the seed user is re-inserted
    to satisfy the NOT NULL owner_id FKs.
    """
    from src.models import SEED_USER_ID

    engine = create_async_engine(test_settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("TRUNCATE " + ", ".join(_ALL_TABLES) + " RESTART IDENTITY CASCADE")
        )
        await conn.execute(
            text("INSERT INTO users (id, label) VALUES (:id, 'local')"),
            {"id": SEED_USER_ID},
        )
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def db_session(
    test_settings: Settings, _clean_db: None
) -> AsyncIterator[AsyncSession]:
    """Async DB session that rolls back after every test.

    Uses a proper AsyncSession backed by its own async engine.  Each test
    runs inside an explicit BEGIN; teardown calls ROLLBACK so the DB stays
    clean for the next test.

    A seed User (id=SEED_USER_ID=1) is inserted before yielding because the
    investigations and audit_log tables have a NOT NULL FK → users.id and the
    brief's prescribed test creates Investigation(name="Op Test") without
    first creating a User row.
    """
    from src.models import SEED_USER_ID, User

    engine = create_async_engine(test_settings.database_url, echo=False)

    # Ensure all tables exist (idempotent; migration has already run).
    async with engine.begin() as setup_conn:
        await setup_conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        async with session.begin():
            # Insert seed user if not present; merge is PK-idempotent.
            seed_user = User(id=SEED_USER_ID, label="local")
            await session.merge(seed_user)

        # Start a fresh transaction for the test body; we will roll it back.
        await session.begin()
        try:
            yield session
        finally:
            # Roll back all test writes; never commits to the live DB.
            await session.rollback()

    await engine.dispose()
