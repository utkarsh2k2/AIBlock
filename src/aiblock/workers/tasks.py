"""Celery tasks for async audio detection.

Each task:
  1. Marks the job as PROCESSING in Redis (fast status update for polling)
  2. Checks S3 cache — skips download if audio already exists
  3. Runs the full pipeline (adapter → preprocess → detect → aggregate)
  4. Uploads audio to S3 for future cache hits
  5. Caches the result in Redis (24 h)
  6. Persists the final result + usage record to PostgreSQL
  7. Updates Redis job status to DONE or FAILED
"""

import json
import logging
import time
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import Task
from sqlalchemy import select

from aiblock.workers.celery_app import celery_app
from aiblock.core import cache, storage
from aiblock.core.models import APIKey, DetectionJob, JobStatus, UsageRecord
from aiblock.config import Config, DetectorConfig
from aiblock.pipeline import build_pipeline, ADAPTER_REGISTRY
from aiblock.settings import get_settings

log = logging.getLogger(__name__)


def _build_config(use_model: bool) -> Config:
    settings = get_settings()
    cfg = Config.from_yaml(Path(settings.default_config_path))
    if use_model:
        cfg.detectors["wav2vec2"] = DetectorConfig(
            model_id="Zeyadd-Mostaffa/Deepfake-Audio-Detection-v1",
            device="cpu",
            weight=3.0,
        )
    return cfg


def _sync_db_session():
    """Return a synchronous SQLAlchemy session for use inside Celery tasks.

    Celery tasks run in a regular (non-async) worker process.
    We use a sync engine here to avoid asyncio event loop conflicts.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    settings = get_settings()
    # Convert asyncpg URL to psycopg2 for sync workers
    sync_url = settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )
    engine = create_engine(sync_url, pool_pre_ping=True, pool_size=2)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


@celery_app.task(
    bind=True,
    name="aiblock.workers.tasks.run_detection",
    max_retries=2,
    default_retry_delay=5,
    soft_time_limit=300,   # 5 min — long audio can take time
    time_limit=360,
)
def run_detection(self: Task, job_id: str, api_key_id: str) -> dict:
    """Run a detection job end-to-end.

    Args:
        job_id: UUID string of the DetectionJob row.
        api_key_id: UUID string of the APIKey row (for usage recording).

    Returns the result dict (also written to DB and Redis).
    """
    session = _sync_db_session()
    started_at = datetime.now(timezone.utc)

    # ── 1. Load job from DB ────────────────────────────────────────────────
    try:
        job: DetectionJob = session.get(DetectionJob, uuid.UUID(job_id))
        if job is None:
            log.error("Job %s not found in DB", job_id)
            return {}

        job.status = JobStatus.PROCESSING
        job.started_at = started_at
        session.commit()

        # Publish fast status update to Redis for polling
        import asyncio
        asyncio.run(cache.set_job_status(job_id, {"status": "processing"}))

    except Exception as exc:
        session.rollback()
        log.exception("Failed to mark job %s as processing", job_id)
        raise

    # ── 2. Check result cache ──────────────────────────────────────────────
    try:
        cached = asyncio.run(
            cache.get_cached_result(job.url, job.platform, job.use_model)
        )
        if cached:
            log.info("Cache hit for job %s", job_id)
            _finalize(session, job, api_key_id, started_at, cached, from_cache=True)
            return cached
    except Exception:
        pass  # cache miss or error — continue to detection

    # ── 3. Run pipeline ────────────────────────────────────────────────────
    try:
        cfg = _build_config(job.use_model)
        pipeline = build_pipeline(job.platform, cfg)

        with tempfile.TemporaryDirectory(prefix="aiblock_worker_") as tmp:
            tmp_path = Path(tmp)

            # Check S3 for pre-downloaded audio
            audio_path = storage.download_audio(job.url, job.platform, tmp_path)

            if audio_path is None:
                # Not in S3 — fetch from platform
                adapter = ADAPTER_REGISTRY[job.platform]()
                audio_path = adapter.fetch(job.url, tmp_path)
                # Upload to S3 for future cache hits
                try:
                    storage.upload_audio(audio_path, job.url, job.platform)
                except Exception:
                    log.warning("S3 upload failed for job %s — continuing", job_id)

            # Get metadata
            try:
                adapter = ADAPTER_REGISTRY[job.platform]()
                metadata = adapter.get_metadata(job.url)
            except Exception:
                metadata = {}

            # Run detection on the local audio file (re-use preprocess + detect)
            from aiblock.preprocessors.audio import preprocess
            from aiblock.aggregator import aggregate

            detectors = pipeline.detectors
            chunks, sr = preprocess(
                audio_path,
                sample_rate=cfg.preprocess.sample_rate,
                chunk_sec=cfg.preprocess.chunk_sec,
            )

            if not chunks:
                result = {"verdict": "Unknown", "score": 0.0, "confidence": 0.0, "chunks": 0}
            else:
                chunk_results = [
                    [d.detect(chunk, sr) for d in detectors]
                    for chunk in chunks
                ]
                result = aggregate(chunk_results, cfg.weights(), cfg.threshold)

        result.update({
            "url": job.url,
            "platform": job.platform,
            "use_model": job.use_model,
            **metadata,
        })

    except Exception as exc:
        log.exception("Detection failed for job %s", job_id)
        _fail(session, job, str(exc))
        asyncio.run(cache.set_job_status(job_id, {"status": "failed", "error": str(exc)}))
        raise self.retry(exc=exc)

    # ── 4. Persist and cache ───────────────────────────────────────────────
    _finalize(session, job, api_key_id, started_at, result)
    try:
        asyncio.run(cache.set_cached_result(job.url, job.platform, job.use_model, result))
    except Exception:
        log.warning("Failed to cache result for job %s", job_id)

    return result


def _finalize(session, job: DetectionJob, api_key_id: str, started_at: datetime, result: dict, from_cache: bool = False) -> None:
    now = datetime.now(timezone.utc)
    job.status = JobStatus.DONE
    job.result = result
    job.completed_at = now
    job.duration_ms = int((now - started_at).total_seconds() * 1000)

    usage = UsageRecord(
        api_key_id=uuid.UUID(api_key_id),
        job_id=job.id,
        platform=job.platform,
        use_model=job.use_model,
        credits_used=0 if from_cache else 1,
        tier_at_time=str(session.get(APIKey, uuid.UUID(api_key_id)).tier),
    )
    session.add(usage)

    import asyncio
    asyncio.run(cache.set_job_status(str(job.id), {"status": "done", "result": result}))

    session.commit()


def _fail(session, job: DetectionJob, error: str) -> None:
    job.status = JobStatus.FAILED
    job.error = error
    job.completed_at = datetime.now(timezone.utc)
    session.commit()
