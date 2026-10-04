"""GET /api/v1/health — application and database status.

Per docs/specifications/api-contracts.md §4 the endpoint must not fail merely because an
optional subsystem (database, LLM provider) is offline; it reports status instead.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.persistence.db import check_database

router = APIRouter(tags=["health"])


class DatabaseHealth(BaseModel):
    ok: bool
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    engine_version: str
    app_env: str
    debug_mode: bool
    database: DatabaseHealth


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    db = await check_database(request.app.state.engine)
    return HealthResponse(
        status="ok" if db.ok else "degraded",
        engine_version=settings.engine_version,
        app_env=settings.app_env,
        debug_mode=settings.debug_mode,
        database=DatabaseHealth(ok=db.ok, latency_ms=db.latency_ms, error=db.error),
    )
