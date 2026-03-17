"""Detection endpoints.

POST /v1/detect        — enqueue an async detection job (all tiers)
POST /v1/detect/sync   — run detection synchronously and return result (Pro+)
GET  /v1/detect/{id}   — poll job status / fetch result
GET  /v1/detect        — list caller's recent jobs
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiblock.api.deps import AuthKey, DBSession
from aiblock.billing.metering import (
    QuotaExceededError,
    ModelNotAllowedError,
    SyncNotAllowedError,
    check_and_consume,
)
from aiblock.core.cache import get_cached_result, get_job_status
from aiblock.core.models import APIKey, DetectionJob, JobStatus

router = APIRouter(prefix="/v1/detect", tags=["detection"])


# ── Request / response schemas ────────────────────────────────────────────────

class DetectRequest(BaseModel):
    url: str = Field(..., description="YouTube or Spotify URL.")
    platform: str = Field(..., description="'youtube' or 'spotify'.")
    use_model: bool = Field(
        False,
        description="Enable wav2vec2 model. Requires Pro tier. Slower but more accurate.",
    )
    min_confidence: float = Field(
        0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Optional lower bound on confidence; clients can treat results below this "
            "as 'gray zone'. The API always returns the raw confidence."
        ),
    )


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    result: Optional[dict] = None
    error: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_platform(platform: str) -> str:
    platform = platform.lower()
    from aiblock.pipeline import ADAPTER_REGISTRY
    if platform not in ADAPTER_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown platform '{platform}'. Supported: {list(ADAPTER_REGISTRY)}",
        )
    return platform


def _quota_error_response(exc: Exception) -> HTTPException:
    if isinstance(exc, QuotaExceededError):
        return HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        )
    if isinstance(exc, ModelNotAllowedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    if isinstance(exc, SyncNotAllowedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    raise exc


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobResponse)
async def enqueue_detection(
    body: DetectRequest,
    key: AuthKey,
    session: DBSession,
):
    """Enqueue an async detection job. Poll GET /v1/detect/{job_id} for the result."""
    platform = _validate_platform(body.platform)

    # Check result cache first — avoid consuming quota for known URLs
    cached = await get_cached_result(body.url, platform, body.use_model)
    if cached:
        # Return a synthetic "done" job without writing to DB or consuming quota
        return JobResponse(
            job_id="cached",
            status="done",
            created_at=datetime.now(timezone.utc),
            result=cached,
        )

    # Enforce tier limits and increment counter
    try:
        await check_and_consume(key, session, use_model=body.use_model)
    except (QuotaExceededError, ModelNotAllowedError, SyncNotAllowedError) as exc:
        raise _quota_error_response(exc)

    # Create DB record
    job = DetectionJob(
        api_key_id=key.id,
        url=body.url,
        platform=platform,
        use_model=body.use_model,
    )
    session.add(job)
    await session.flush()  # get job.id without committing yet

    # Enqueue Celery task
    from aiblock.workers.tasks import run_detection
    task = run_detection.apply_async(
        args=[str(job.id), str(key.id)],
        task_id=str(job.id),  # use job ID as task ID for easy lookups
    )
    job.celery_task_id = task.id
    await session.commit()

    return JobResponse(
        job_id=str(job.id),
        status="pending",
        created_at=job.created_at,
    )


@router.post("/sync", response_model=dict)
async def detect_sync(
    body: DetectRequest,
    key: AuthKey,
    session: DBSession,
):
    """Run detection synchronously and return the result immediately.

    Requires Pro tier. Blocks until detection completes (up to 5 minutes for long audio).
    For user-facing tools and MCP agents where latency is acceptable.
    """
    platform = _validate_platform(body.platform)

    # Check cache first
    cached = await get_cached_result(body.url, platform, body.use_model)
    if cached:
        return cached

    try:
        await check_and_consume(key, session, use_model=body.use_model, sync=True)
    except (QuotaExceededError, ModelNotAllowedError, SyncNotAllowedError) as exc:
        raise _quota_error_response(exc)

    # Run pipeline directly in the request (only safe for Pro+ with short audio)
    import asyncio
    from pathlib import Path
    from aiblock.config import Config, DetectorConfig
    from aiblock.pipeline import build_pipeline
    from aiblock.settings import get_settings

    settings = get_settings()
    cfg = Config.from_yaml(Path(settings.default_config_path))
    if body.use_model:
        cfg.detectors["wav2vec2"] = DetectorConfig(
            model_id="Zeyadd-Mostaffa/Deepfake-Audio-Detection-v1",
            device="cpu",
            weight=3.0,
        )

    loop = asyncio.get_event_loop()
    pipeline = build_pipeline(platform, cfg)
    result = await loop.run_in_executor(None, pipeline.run, body.url)

    # Enrich with metadata
    from aiblock.pipeline import ADAPTER_REGISTRY
    adapter = ADAPTER_REGISTRY[platform]()
    try:
        metadata = await loop.run_in_executor(None, adapter.get_metadata, body.url)
        result.update(metadata)
    except Exception:
        pass

    result.update({"url": body.url, "platform": platform, "use_model": body.use_model})

    # Record job + usage in DB
    job = DetectionJob(
        api_key_id=key.id,
        url=body.url,
        platform=platform,
        use_model=body.use_model,
        status=JobStatus.DONE,
        result=result,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(job)

    from aiblock.billing.metering import record_usage
    await record_usage(key, job, session)
    await session.commit()

    return result


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    key: AuthKey,
    session: DBSession,
):
    """Poll a job's status. Returns result when status == 'done'."""
    # Fast path: Redis
    redis_data = await get_job_status(job_id)
    if redis_data:
        job_status = redis_data.get("status", "pending")
        return JobResponse(
            job_id=job_id,
            status=job_status,
            created_at=datetime.now(timezone.utc),
            result=redis_data.get("result"),
            error=redis_data.get("error"),
        )

    # Slow path: DB (for completed jobs where Redis TTL expired)
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    job: DetectionJob | None = await session.get(DetectionJob, job_uuid)
    if job is None or job.api_key_id != key.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    return JobResponse(
        job_id=str(job.id),
        status=job.status,
        created_at=job.created_at,
        result=job.result,
        error=job.error,
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    key: AuthKey,
    session: DBSession,
    limit: int = 20,
    offset: int = 0,
):
    """List the caller's recent detection jobs."""
    from sqlalchemy import func

    stmt = (
        select(DetectionJob)
        .where(DetectionJob.api_key_id == key.id)
        .order_by(DetectionJob.created_at.desc())
        .offset(offset)
        .limit(min(limit, 100))
    )
    count_stmt = (
        select(func.count(DetectionJob.id))
        .where(DetectionJob.api_key_id == key.id)
    )

    jobs = (await session.execute(stmt)).scalars().all()
    total: int = (await session.execute(count_stmt)).scalar_one()

    return JobListResponse(
        jobs=[
            JobResponse(
                job_id=str(j.id),
                status=j.status,
                created_at=j.created_at,
                result=j.result,
                error=j.error,
            )
            for j in jobs
        ],
        total=total,
    )
