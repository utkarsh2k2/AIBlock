"""Redis client for caching detection results and rate-limit counters.

Design:
  - Detection results are cached by (url, platform, use_model) → JSON for 24 h.
    This prevents re-downloading and re-analysing the same URL within a day.
  - Rate-limit counters use Redis INCR + EXPIRE for atomic per-key windowing.
"""

import json
import hashlib
from typing import Any, Optional

import redis.asyncio as aioredis

from aiblock.settings import get_settings

_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _result_cache_key(url: str, platform: str, use_model: bool) -> str:
    digest = hashlib.sha256(f"{url}|{platform}|{use_model}".encode()).hexdigest()[:16]
    return f"aiblock:result:{digest}"


async def get_cached_result(url: str, platform: str, use_model: bool) -> Optional[dict]:
    key = _result_cache_key(url, platform, use_model)
    raw = await get_redis().get(key)
    return json.loads(raw) if raw else None


async def set_cached_result(url: str, platform: str, use_model: bool, result: dict) -> None:
    settings = get_settings()
    key = _result_cache_key(url, platform, use_model)
    await get_redis().set(key, json.dumps(result), ex=settings.cache_result_ttl_seconds)


# ── Job status helpers ─────────────────────────────────────────────────────────

def _job_key(job_id: str) -> str:
    return f"aiblock:job:{job_id}"


async def set_job_status(job_id: str, data: dict) -> None:
    settings = get_settings()
    await get_redis().set(_job_key(job_id), json.dumps(data), ex=settings.job_ttl_seconds)


async def get_job_status(job_id: str) -> Optional[dict]:
    raw = await get_redis().get(_job_key(job_id))
    return json.loads(raw) if raw else None


# ── Rate-limit helpers ─────────────────────────────────────────────────────────

async def increment_rate_limit(key_id: str, window_seconds: int = 60) -> int:
    """Increment per-minute request counter. Returns new count.

    Uses a sliding-window approach: key expires after `window_seconds`.
    """
    redis_key = f"aiblock:rl:{key_id}:{window_seconds}"
    pipe = get_redis().pipeline()
    pipe.incr(redis_key)
    pipe.expire(redis_key, window_seconds)
    results = await pipe.execute()
    return results[0]  # new counter value
