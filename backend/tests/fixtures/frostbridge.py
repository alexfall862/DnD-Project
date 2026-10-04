"""The Frostbridge tavern fixture for the knowledge-leakage matrix and the orchestrator tests.
The seed itself lives in `app.seeds.frostbridge_tavern` (shared with the CLI harness and
`make seed-demo`); this module only wraps it as a pytest fixture."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.seeds.frostbridge_tavern import (
    BEHAVIOR,
    FROSTBRIDGE_BUILDS,
    TAVERN_SPACE,
    SeededWorld,
    seed_tavern,
)

World = SeededWorld

__all__ = ["BEHAVIOR", "FROSTBRIDGE_BUILDS", "TAVERN_SPACE", "World", "frostbridge"]


@pytest_asyncio.fixture
async def frostbridge(session: AsyncSession) -> World:
    return await seed_tavern(session, name="leakage", engine_version="test")
