"""Alembic environment configuration with async support.

The database URL and connection are managed through SQLAlchemy's async API so
that migrations run against the same ``asyncpg`` driver used by the
application at runtime.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import application settings and declarative base so that autogenerate can
# discover model metadata.
from app.core.config import settings
from app.core.database import Base

# Make sure all model modules are imported so their tables are registered on
# `Base.metadata`. Add future feature model imports here as they are created.
# import app.modules.<feature>.models  # noqa: F401  (example)
import app.modules.users.models  # noqa: F401
import app.modules.article.models  # noqa: F401
import app.modules.reading.models  # noqa: F401
import app.modules.ai.models  # noqa: F401
import app.modules.llm_config.models  # noqa: F401
import app.agents.modules.models  # noqa: F401

config = context.config

# Inject the runtime database URL from application settings.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configure and run migrations against an open connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode using an async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
