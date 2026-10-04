"""Alembic environment (async engine).

Database URL resolution order: `ALEMBIC_DATABASE_URL` env var → `-x url=...` → settings.
Migrations are grouped per docs/specifications/database-schema.md §23; `0000_extensions`
precedes that list.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.persistence.models import Base

config = context.config

target_metadata = Base.metadata


def _resolve_url() -> str:
    url = os.environ.get("ALEMBIC_DATABASE_URL")
    if not url:
        url = context.get_x_argument(as_dictionary=True).get("url")
    if not url:
        url = get_settings().database_url
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {}) or {}
    section["sqlalchemy.url"] = _resolve_url()
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(_run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
