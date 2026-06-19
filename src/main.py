"""FastAPI application factory.

Wires together: structured logging, settings, cipher, DB engine/session-maker,
and the app itself.  Routers are mounted in later tasks.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from src.core.config import get_settings
from src.core.crypto import EncryptedString, FieldCipher
from src.core.db import make_engine, make_session_maker, set_session_maker
from src.core.logging import configure_logging

# URL prefixes that bypass the authorization gate.
_EXEMPT_PREFIXES = ("/authorize", "/static", "/healthz", "/v1")


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

    # Mount vendored static assets (htmx, cytoscape, app.css).
    # The directory must exist before mounting; StaticFiles raises on startup
    # otherwise.  The directory is created as part of the task scaffold.
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    from src.api.web import pages

    app.include_router(pages.router)

    # Authorization-gate middleware.  Any path not starting with an exempt
    # prefix requires the osint_authorized cookie (set by POST /authorize).
    # Middleware is applied in reverse registration order in Starlette, so
    # registering last means it runs first on every inbound request.
    async def _gate(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path.startswith(_EXEMPT_PREFIXES) or request.cookies.get(
            "osint_authorized"
        ):
            return await call_next(request)
        return RedirectResponse("/authorize", status_code=307)

    app.add_middleware(BaseHTTPMiddleware, dispatch=_gate)

    return app
