"""FastAPI dependency injection: authentication, database sessions, rate limiting.

All route handlers that require auth use `Depends(require_api_key)`.
The API key is passed via the Authorization header:
    Authorization: Bearer abl_live_<key>
or via the X-API-Key header:
    X-API-Key: abl_live_<key>
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiblock.core.cache import increment_rate_limit
from aiblock.core.db import get_session
from aiblock.core.models import APIKey
from aiblock.billing.tiers import get_tier


# ── Database session ──────────────────────────────────────────────────────────

async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(db_session)]


# ── API key authentication ─────────────────────────────────────────────────────

def _extract_raw_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    raw: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    elif x_api_key:
        raw = x_api_key.strip()

    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Pass it via 'Authorization: Bearer <key>' or 'X-API-Key: <key>'.",
        )
    return raw


async def require_api_key(
    raw_key: Annotated[str, Depends(_extract_raw_key)],
    session: DBSession,
) -> APIKey:
    """Resolve an API key from the request and validate it.

    Raises 401 if the key is missing/invalid/revoked.
    Raises 429 if the per-minute rate limit is exceeded.
    """
    key_hash = APIKey.hash_key(raw_key)
    stmt = select(APIKey).where(APIKey.key_hash == key_hash)
    result = await session.execute(stmt)
    key: APIKey | None = result.scalar_one_or_none()

    if key is None or not key.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key.",
        )

    # Per-minute rate limiting (Redis INCR)
    tier_cfg = get_tier(key.tier)
    count = await increment_rate_limit(str(key.id), window_seconds=60)
    if count > tier_cfg.rate_limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {tier_cfg.rate_limit_per_minute} req/min on {key.tier} tier.",
            headers={"Retry-After": "60"},
        )

    return key


AuthKey = Annotated[APIKey, Depends(require_api_key)]
