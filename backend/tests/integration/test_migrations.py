"""Migration up/down smoke test against the test database.

Synchronous on purpose: Alembic's async env calls `asyncio.run`, which cannot run inside an
already-running event loop.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

from app.config import Settings

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()  # equivalent of `-x url=...`
    return cfg


def _installed_extensions(url: str) -> set[str]:
    async def query() -> set[str]:
        conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            return {r["extname"] for r in await conn.fetch("SELECT extname FROM pg_extension")}
        finally:
            await conn.close()

    return asyncio.run(query())


def test_migrations_upgrade_and_downgrade(require_test_db: None, test_settings: Settings) -> None:
    url = test_settings.database_url
    cfg = _alembic_config(url)

    command.downgrade(cfg, "base")
    assert "vector" not in _installed_extensions(url)

    command.upgrade(cfg, "head")
    assert {"vector", "pgcrypto"} <= _installed_extensions(url)

    command.downgrade(cfg, "base")
    assert "vector" not in _installed_extensions(url)

    command.upgrade(cfg, "head")  # leave the test database migrated for later tests
