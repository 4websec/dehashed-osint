"""FastAPI application factory.

Wires together: structured logging, settings, cipher, DB engine/session-maker,
and the app itself.  Routers are mounted in later tasks.
"""

from fastapi import FastAPI

from src.core.config import get_settings
from src.core.crypto import EncryptedString, FieldCipher
from src.core.db import make_engine, make_session_maker, set_session_maker
from src.core.logging import configure_logging


def create_app() -> FastAPI:
    """Construct and return the configured FastAPI application.

    Intentionally does NOT open a DB connection — create_async_engine is lazy,
    so the /healthz endpoint works without Postgres present.
    """
    configure_logging()

    settings = get_settings()

    # Configure the symmetric cipher used by EncryptedString columns.
    EncryptedString.configure(FieldCipher(settings.encryption_key.get_secret_value()))

    # Build the async engine + session-maker and register globally so
    # get_session() dependency injection works everywhere.
    engine = make_engine(settings.database_url)
    set_session_maker(make_session_maker(engine))

    app = FastAPI(title="DeHashed OSINT Platform")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        """Liveness probe — no DB I/O, always fast."""
        return {"status": "ok"}

    from src.api.v1 import investigations, searches

    app.include_router(investigations.router)
    app.include_router(searches.router)

    return app
