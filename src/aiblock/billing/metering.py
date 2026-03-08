"""Usage metering and limit enforcement.

Checks tier limits before allowing a job to proceed.
Records usage after a job completes.
Month-boundary resets are handled lazily (checked on each request).
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from aiblock.billing.tiers import TierConfig, get_tier
from aiblock.core.models import APIKey, DetectionJob, JobStatus, UsageRecord


class QuotaExceededError(Exception):
    """Raised when a request would exceed the API key's monthly quota."""
    def __init__(self, limit: int, used: int):
        self.limit = limit
        self.used = used
        super().__init__(f"Monthly quota exceeded: {used}/{limit} requests used.")


class ModelNotAllowedError(Exception):
    """Raised when the requested model is not in the key's tier."""
    def __init__(self, model: str, tier: str):
        super().__init__(f"Model '{model}' is not available on the {tier} tier.")


class SyncNotAllowedError(Exception):
    """Raised when sync detection is requested on a tier that doesn't support it."""
    def __init__(self, tier: str):
        super().__init__(
            f"Synchronous detection is not available on the {tier} tier. "
            "Upgrade to Pro or use the async endpoint."
        )


async def _reset_if_new_month(key: APIKey, session: AsyncSession) -> None:
    """Lazy monthly reset: if the reset timestamp is in a past month, zero the counter."""
    now = datetime.now(timezone.utc)
    reset = key.month_reset_at.replace(tzinfo=timezone.utc) if key.month_reset_at.tzinfo is None else key.month_reset_at
    if now.year > reset.year or now.month > reset.month:
        key.requests_this_month = 0
        key.month_reset_at = now
        await session.flush()


async def check_and_consume(
    key: APIKey,
    session: AsyncSession,
    *,
    use_model: bool = False,
    sync: bool = False,
) -> None:
    """Enforce tier limits. Raises on violation; increments counter on success.

    Call this BEFORE enqueuing a job.
    """
    tier_cfg: TierConfig = get_tier(key.tier)

    await _reset_if_new_month(key, session)

    # Model gate
    if use_model and "wav2vec2" not in tier_cfg.allowed_models:
        raise ModelNotAllowedError("wav2vec2", key.tier)

    # Sync gate
    if sync and not tier_cfg.sync_allowed:
        raise SyncNotAllowedError(key.tier)

    # Monthly quota
    if tier_cfg.monthly_limit is not None:
        if key.requests_this_month >= tier_cfg.monthly_limit:
            raise QuotaExceededError(tier_cfg.monthly_limit, key.requests_this_month)

    key.requests_this_month += 1
    await session.flush()


async def record_usage(
    key: APIKey,
    job: DetectionJob,
    session: AsyncSession,
) -> None:
    """Write an immutable UsageRecord after a job completes successfully."""
    record = UsageRecord(
        api_key_id=key.id,
        job_id=job.id,
        platform=job.platform,
        use_model=job.use_model,
        credits_used=1,
        tier_at_time=key.tier,
    )
    session.add(record)
    await session.flush()


async def get_usage_summary(key_id: UUID, session: AsyncSession) -> dict:
    """Return usage statistics for a given API key."""
    now = datetime.now(timezone.utc)

    # Jobs this month
    stmt = (
        select(func.count(DetectionJob.id))
        .join(APIKey, DetectionJob.api_key_id == APIKey.id)
        .where(
            DetectionJob.api_key_id == key_id,
            DetectionJob.created_at >= datetime(now.year, now.month, 1, tzinfo=timezone.utc),
            DetectionJob.status == JobStatus.DONE,
        )
    )
    jobs_this_month: int = (await session.execute(stmt)).scalar_one()

    key_stmt = select(APIKey).where(APIKey.id == key_id)
    key: APIKey = (await session.execute(key_stmt)).scalar_one()
    tier_cfg: TierConfig = get_tier(key.tier)

    return {
        "tier": key.tier,
        "requests_this_month": jobs_this_month,
        "monthly_limit": tier_cfg.monthly_limit,
        "remaining": (
            max(0, tier_cfg.monthly_limit - jobs_this_month)
            if tier_cfg.monthly_limit is not None
            else None
        ),
    }
