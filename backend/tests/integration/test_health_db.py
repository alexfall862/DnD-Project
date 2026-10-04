"""Health endpoint against the real test database."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_health_ok_with_database(require_test_db: None, client: AsyncClient) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"]["ok"] is True
    assert body["database"]["latency_ms"] is not None
    assert body["app_env"] == "test"
