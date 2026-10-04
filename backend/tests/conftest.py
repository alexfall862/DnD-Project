"""Shared fixtures.

- `unit` tests never touch a database or provider.
- `integration` / `invariants` / `leakage` tests use the real `ttrpg_test` database
  (docs/testing/testing-strategy.md §4), migrated to head once per session, and are skipped
  with a clear message when it is unreachable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.main import create_app
from app.persistence.db import make_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--eval", action="store_true", default=False, help="run real-model evals")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--eval"):
        return
    skip = pytest.mark.skip(reason="real-model eval; run with --eval (make eval-local)")
    for item in items:
        if "eval" in item.keywords:
            item.add_marker(skip)


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={url}"]})()  # equivalent of `-x url=...`
    return cfg


@pytest.fixture(scope="session")
def base_settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def test_settings(base_settings: Settings) -> Settings:
    """Settings pointed at the test database."""
    return base_settings.model_copy(
        update={"app_env": "test", "database_url": base_settings.test_database_url}
    )


@pytest_asyncio.fixture(scope="session")
async def test_db_available(test_settings: Settings) -> bool:
    engine = make_engine(test_settings.database_url, connect_timeout_s=3)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        return False
    finally:
        await engine.dispose()


@pytest.fixture
def require_test_db(test_db_available: bool, test_settings: Settings) -> None:
    if not test_db_available:
        pytest.skip(f"test database unreachable at {test_settings.database_url} (run `make db-up`)")


@pytest.fixture(scope="session")
def migrated_db(test_db_available: bool, test_settings: Settings) -> str:
    """Ensure the test database is at head once per session. Returns its URL."""
    if not test_db_available:
        pytest.skip(f"test database unreachable at {test_settings.database_url}")
    command.upgrade(alembic_config(test_settings.database_url), "head")
    return test_settings.database_url


@pytest_asyncio.fixture(scope="session")
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(migrated_db)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def client(test_settings: Settings, migrated_db: str) -> AsyncIterator[AsyncClient]:
    """HTTP client against an app wired to the (migrated) test database, with lifespan run."""
    app = create_app(test_settings)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
