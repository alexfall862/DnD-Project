"""Async SQLAlchemy engine and session management."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(url: str, *, connect_timeout_s: float = 5.0, echo: bool = False) -> AsyncEngine:
    """Create an async engine. Connection attempts are bounded so health checks stay fast."""
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        connect_args={"timeout": connect_timeout_s},
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@dataclass(frozen=True)
class DatabaseStatus:
    ok: bool
    latency_ms: float | None
    error: str | None = None


async def check_database(engine: AsyncEngine) -> DatabaseStatus:
    """Round-trip a trivial query. Never raises; the health endpoint reports the outcome."""
    started = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health must report, not propagate
        return DatabaseStatus(ok=False, latency_ms=None, error=f"{type(exc).__name__}: {exc}")
    return DatabaseStatus(ok=True, latency_ms=round((time.perf_counter() - started) * 1000, 2))


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        yield session
