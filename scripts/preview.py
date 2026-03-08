"""Preview server — runs the full AIBlock API with SQLite + in-memory Redis.

No Docker, no PostgreSQL, no Redis needed.
Swagger UI: http://localhost:8000/docs

Usage:
  python scripts/preview.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

# ── Point to src so aiblock is importable ─────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ── Override settings before anything imports them ────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./preview.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")  # mocked below
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEBUG", "true")

# ── In-memory Redis mock ───────────────────────────────────────────────────────
_store: dict[str, tuple[str, float | None]] = {}  # key → (value, expiry_ts | None)


class _FakeRedis:
    async def get(self, key):
        entry = _store.get(key)
        if entry is None:
            return None
        val, exp = entry
        if exp is not None and time.time() > exp:
            del _store[key]
            return None
        return val

    async def set(self, key, value, ex=None):
        exp = (time.time() + ex) if ex else None
        _store[key] = (value, exp)

    async def incr(self, key):
        entry = _store.get(key)
        if entry is None:
            _store[key] = ("1", None)
            return 1
        val, exp = entry
        new_val = str(int(val) + 1)
        _store[key] = (new_val, exp)
        return int(new_val)

    async def expire(self, key, seconds):
        if key in _store:
            val, _ = _store[key]
            _store[key] = (val, time.time() + seconds)

    async def ping(self):
        return True

    async def aclose(self):
        pass

    def pipeline(self):
        return _FakePipeline()


class _FakePipeline:
    def __init__(self):
        self._cmds = []

    def incr(self, key):
        self._cmds.append(("incr", key))
        return self

    def expire(self, key, seconds):
        self._cmds.append(("expire", key, seconds))
        return self

    async def execute(self):
        results = []
        fake = _FakeRedis()
        for cmd in self._cmds:
            if cmd[0] == "incr":
                results.append(await fake.incr(cmd[1]))
            elif cmd[0] == "expire":
                await fake.expire(cmd[1], cmd[2])
                results.append(True)
        return results


_fake_redis = _FakeRedis()


# Patch cache module before it's imported
import aiblock.core.cache as _cache_mod
_cache_mod.get_redis = lambda: _fake_redis

# ── Stub out Celery so the detect route runs jobs inline ──────────────────────
# In preview mode there's no Celery worker; tasks run synchronously inline.
import types, sys as _sys

_celery_stub = types.ModuleType("celery")
_celery_stub.Task = object

class _FakeCeleryApp:
    def task(self, *a, **kw):
        def decorator(fn):
            def apply_async(args=(), kwargs=None, **opts):
                class _R:
                    id = "preview-inline"
                return _R()
            fn.apply_async = apply_async
            return fn
        return decorator
    def config_from_object(self, *a, **kw): pass
    def autodiscover_tasks(self, *a, **kw): pass

_celery_stub.Celery = lambda *a, **kw: _FakeCeleryApp()
_sys.modules.setdefault("celery", _celery_stub)
_sys.modules.setdefault("celery.app", _celery_stub)

# Patch workers.tasks to run detection inline instead of via Celery
import aiblock.workers.tasks as _tasks_mod

def _inline_run_detection(job_id: str, api_key_id: str) -> dict:
    """Preview stub: runs detection synchronously in the same process."""
    import uuid as _uuid
    from datetime import datetime, timezone
    from pathlib import Path as _Path
    from aiblock.core.models import DetectionJob, JobStatus, UsageRecord, APIKey
    from aiblock.config import Config, DetectorConfig
    from aiblock.pipeline import build_pipeline

    session = _tasks_mod._sync_db_session()
    job = session.get(DetectionJob, _uuid.UUID(job_id))
    if job is None:
        return {}

    job.status = JobStatus.PROCESSING
    job.started_at = datetime.now(timezone.utc)
    session.commit()

    try:
        cfg = _tasks_mod._build_config(job.use_model)
        import tempfile
        with tempfile.TemporaryDirectory(prefix="aiblock_preview_") as tmp:
            from aiblock.pipeline import ADAPTER_REGISTRY
            adapter = ADAPTER_REGISTRY[job.platform]()
            audio_path = adapter.fetch(job.url, _Path(tmp))
            metadata = {}
            try:
                metadata = adapter.get_metadata(job.url)
            except Exception:
                pass

            from aiblock.preprocessors.audio import preprocess
            from aiblock.aggregator import aggregate

            pl = build_pipeline(job.platform, cfg)
            chunks, sr = preprocess(audio_path, sample_rate=cfg.preprocess.sample_rate, chunk_sec=cfg.preprocess.chunk_sec)
            if not chunks:
                result = {"verdict": "Unknown", "score": 0.0, "confidence": 0.0, "chunks": 0}
            else:
                chunk_results = [[d.detect(c, sr) for d in pl.detectors] for c in chunks]
                result = aggregate(chunk_results, cfg.weights(), cfg.threshold)

        result.update({"url": job.url, "platform": job.platform, "use_model": job.use_model, **metadata})
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        session.commit()
        return {}

    now = datetime.now(timezone.utc)
    job.status = JobStatus.DONE
    job.result = result
    job.completed_at = now
    job.duration_ms = int((now - job.started_at).total_seconds() * 1000)
    key = session.get(APIKey, _uuid.UUID(api_key_id))
    usage = UsageRecord(api_key_id=_uuid.UUID(api_key_id), job_id=job.id, platform=job.platform,
                        use_model=job.use_model, credits_used=1,
                        tier_at_time=str(key.tier) if key else "free")
    session.add(usage)
    session.commit()
    return result

class _InlineTask:
    id = "preview-task"
    def apply_async(self, args=(), **opts):
        # Run inline synchronously for preview
        _inline_run_detection(*args)
        class _R:
            id = args[0] if args else "preview"
        return _R()

_tasks_mod.run_detection = _InlineTask()

# ── Patch SQLAlchemy to use SQLite (async) ────────────────────────────────────
# SQLAlchemy 2.0 with aiosqlite needs the event_engine tweak for SQLite
import aiblock.core.db as _db_mod
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from contextlib import asynccontextmanager

_sqlite_engine = create_async_engine(
    "sqlite+aiosqlite:///./preview.db",
    echo=False,
    connect_args={"check_same_thread": False},
)
_sqlite_factory = async_sessionmaker(_sqlite_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def _sqlite_session():
    async with _sqlite_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


_db_mod._get_engine = lambda: _sqlite_engine
_db_mod._get_session_factory = lambda: _sqlite_factory
_db_mod.get_session = _sqlite_session


async def _create_sqlite_tables():
    from aiblock.core.models import Base
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB

    # SQLite doesn't support JSONB — replace it with JSON for preview
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()

    async with _sqlite_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Create and run the app ─────────────────────────────────────────────────────
async def main():
    await _create_sqlite_tables()
    print("\n" + "=" * 60)
    print("  AIBlock Preview API")
    print("=" * 60)
    print("  Swagger UI:  http://localhost:8000/docs")
    print("  ReDoc:       http://localhost:8000/redoc")
    print("  Health:      http://localhost:8000/health")
    print("=" * 60)
    print("  Backend: SQLite (preview.db) + in-memory cache")
    print("  Detection tasks run synchronously (no Celery worker needed)")
    print("=" * 60 + "\n")

    import uvicorn
    from aiblock.api.app import create_app

    app = create_app()
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
