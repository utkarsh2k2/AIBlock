"""Async SQLAlchemy engine and session factory.

Usage in FastAPI:
    async with get_session() as session:
        result = await session.execute(select(User))
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from aiblock.settings import get_settings

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # reconnect on stale connections
            echo=settings.debug,
        )
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager yielding a database session."""
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables() -> None:
    """Create all tables. Called on app startup in development; use Alembic in production."""
    from aiblock.core.models import Base  # noqa: F401 — registers all models

    async with _get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Dispose the engine connection pool. Called on app shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
