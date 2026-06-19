import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Alembic Config object; provides access to .ini values.
config = context.config

# Set up Python logging from the ini file.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Project imports ──────────────────────────────────────────────────────────
# Import Base and all models so every table registers on Base.metadata before
# autogenerate inspects it.
from src.core.config import get_settings  # noqa: E402
from src.core.db import Base  # noqa: E402
import src.models  # noqa: F401, E402  – side-effect: registers ORM classes

target_metadata = Base.metadata

# Override the URL from application settings so we don't hardcode creds in
# alembic.ini.  get_settings() reads from .env / environment variables.
_settings = get_settings()
config.set_main_option("sqlalchemy.url", _settings.database_url)


# ── Offline mode ─────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection (useful for dry-runs)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode (async) ───────────────────────────────────────────────────────
def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via a sync connection proxy."""
    url = config.get_main_option("sqlalchemy.url")
    engine = create_async_engine(url, poolclass=None)  # NullPool equivalent

    async with engine.connect() as conn:
        # run_sync hands a regular synchronous Connection to the callback,
        # which is what context.configure / run_migrations expect.
        await conn.run_sync(do_run_migrations)

    await engine.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration; bridges sync Alembic → async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
