"""Alembic environment — supports async SQLAlchemy with asyncpg.

Run migrations:
  alembic upgrade head

Create a new migration after model changes:
  alembic revision --autogenerate -m "describe change here"
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Config ─────────────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override URL from environment (replaces %(DATABASE_URL)s in alembic.ini)
database_url = os.environ.get("DATABASE_URL", "")
if database_url:
    # Convert asyncpg URL to asyncpg for alembic (it can run async migrations)
    config.set_main_option("sqlalchemy.url", database_url)

# Import all models so autogenerate can detect them
from aiblock.core.models import Base  # noqa: F401

target_metadata = Base.metadata


# ── Offline migrations (generate SQL without connecting) ──────────────────────
def run_migrations_offline() -> None:
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


# ── Online migrations (connect and run) ───────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
