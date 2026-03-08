"""FastAPI application factory.

Usage:
  uvicorn aiblock.api.app:create_app --factory --host 0.0.0.0 --port 8000
  # or via CLI:
  aiblock serve
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aiblock.settings import get_settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup and shutdown lifecycle hooks."""
    settings = get_settings()
    log.info("Starting AIBlock API (%s)", settings.environment)

    # Warm DB connection pool
    from aiblock.core.db import create_tables
    if settings.environment == "development":
        await create_tables()  # auto-create in dev; use Alembic in prod

    yield  # app is running

    # Shutdown: close connection pools
    from aiblock.core.db import dispose_engine
    from aiblock.core.cache import close_redis
    await dispose_engine()
    await close_redis()
    log.info("AIBlock API shut down cleanly.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AIBlock API",
        description=(
            "Detect AI-generated audio on YouTube and Spotify. "
            "Modular, agent-friendly, and extensible to video, text, and images."
        ),
        version="1.0.0",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
        lifespan=_lifespan,
    )

    # ── Middleware ─────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ─────────────────────────────────────────────────────────────
    from aiblock.api.routes.health import router as health_router
    from aiblock.api.routes.detect import router as detect_router
    from aiblock.api.routes.keys import router as keys_router
    from aiblock.api.routes.webhooks import router as webhooks_router

    app.include_router(health_router)
    app.include_router(detect_router)
    app.include_router(keys_router)
    app.include_router(webhooks_router)

    # ── Exception handlers ─────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        log.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error. Please try again."},
        )

    return app
