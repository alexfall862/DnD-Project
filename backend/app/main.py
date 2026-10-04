"""FastAPI application factory.

`create_app(settings)` builds an isolated app with its own engine so tests can point it at the
test database (or at nothing) without touching globals. `app` is the uvicorn entry point.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import router as api_v1_router
from app.config import Settings, get_settings
from app.persistence.db import make_engine, make_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url, connect_timeout_s=settings.db_connect_timeout_s)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="AI TTRPG Engine",
        version=settings.engine_version,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.include_router(api_v1_router)
    return app


app = create_app()
