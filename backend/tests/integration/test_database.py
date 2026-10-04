"""Database connectivity and the pgvector image."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.config import Settings
from app.persistence.db import check_database, make_engine

pytestmark = pytest.mark.integration


async def test_connect_and_vector_extension_available(
    require_test_db: None, test_settings: Settings
) -> None:
    engine = make_engine(test_settings.database_url)
    try:
        status = await check_database(engine)
        assert status.ok, status.error
        async with engine.connect() as conn:
            version = (await conn.execute(text("SHOW server_version"))).scalar_one()
            query = text(
                "SELECT name FROM pg_available_extensions WHERE name IN ('vector', 'pgcrypto')"
            )
            available = (await conn.execute(query)).scalars().all()
        assert int(version.split(".")[0]) >= 16
        assert set(available) == {"vector", "pgcrypto"}, "use the pgvector/pgvector image"
    finally:
        await engine.dispose()
