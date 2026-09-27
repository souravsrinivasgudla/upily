"""
Alembic environment.

Two entry points:
  * CLI (`alembic upgrade head`): builds its own async engine from the app settings.
  * App startup (db/database.py:init_db): passes an already-open sync connection via
    `config.attributes["connection"]`, so migrations run inside the app's event loop.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from db import models  # noqa: F401 — registers tables on Base.metadata
from db.database import DATABASE_URL, Base

config = context.config
target_metadata = Base.metadata


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        render_as_batch=True,    # SQLite can't ALTER most things; batch mode recreates the table
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    _configure(url=DATABASE_URL, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
elif (connection := config.attributes.get("connection")) is not None:
    do_run_migrations(connection)
else:
    if config.config_file_name:
        fileConfig(config.config_file_name)   # CLI only — don't override the app's logging
    asyncio.run(run_async_migrations())
