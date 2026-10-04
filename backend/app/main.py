"""FastAPI application factory.

`create_app(settings)` builds an isolated app with its own engine so tests can point it at the
test database (or at nothing) without touching globals. `app` is the uvicorn entry point.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.ai.embeddings import A9Embedder
from app.ai.providers import A9Provider, FakeModelProvider
from app.api.errors import install as install_error_handling
from app.api.v1 import router as api_v1_router
from app.config import Settings, get_settings
from app.engine.core import RulesEngine
from app.persistence.db import make_engine, make_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url, connect_timeout_s=settings.db_connect_timeout_s)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.rules_engine = RulesEngine.load(settings.default_ruleset)
        # Providers: A9 when a token is configured; otherwise a fake that tests replace.
        if settings.a9_token:
            app.state.provider = A9Provider(
                settings.a9_base_url,
                settings.a9_token,
                client_name=settings.a9_client_name,
                max_concurrent=settings.max_concurrent_inference,
            )
            app.state.embedder = A9Embedder(
                settings.a9_base_url,
                settings.a9_token,
                client_name=settings.a9_client_name,
                model=settings.model_profile_embedding,
                rerank_model=settings.model_profile_rerank,
                dimensions=settings.embedding_dimensions,
            )
        else:
            app.state.provider = FakeModelProvider()
            app.state.embedder = None
        try:
            yield
        finally:
            for closable in (
                getattr(app.state, "provider", None),
                getattr(app.state, "embedder", None),
            ):
                if hasattr(closable, "aclose"):
                    await closable.aclose()
            await engine.dispose()

    app = FastAPI(
        title="AI TTRPG Engine",
        version=settings.engine_version,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    install_error_handling(app)
    app.include_router(api_v1_router)
    return app


app = create_app()
