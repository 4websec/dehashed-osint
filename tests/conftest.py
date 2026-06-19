"""Shared pytest fixtures for the test suite.

Task 4 provides the foundational seam here: Settings construction with a live
generated key, EncryptedString cipher configuration, and an async db_session
fixture that rolls back after each test to keep the DB clean.

Task 5 will extend this file rather than recreate it.
"""

import base64
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import Settings
from src.core.crypto import EncryptedString, FieldCipher
from src.core.db import Base


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Build Settings directly with a generated key; no real .env required."""
    key = base64.b64encode(os.urandom(32)).decode()
    return Settings(
        dehashed_api_key="test-placeholder",  # type: ignore[arg-type]
        database_url="postgresql+asyncpg://osint:osint@localhost:5432/osint",
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


@pytest_asyncio.fixture
async def db_session(test_settings: Settings) -> AsyncIterator[AsyncSession]:
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
