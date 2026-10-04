"""Health endpoint reports a missing database instead of failing (api-contracts §4)."""

from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.unit


async def test_health_is_degraded_without_database() -> None:
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nowhere",
        db_connect_timeout_s=1,
    )
    app = create_app(settings)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["database"]["ok"] is False
    assert body["database"]["error"]
    assert body["engine_version"] == settings.engine_version
