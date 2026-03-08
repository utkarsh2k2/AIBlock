"""API key management endpoints.

POST   /v1/keys          — create a new API key (returned raw key shown once)
GET    /v1/keys          — list caller's keys
DELETE /v1/keys/{key_id} — revoke a key
GET    /v1/usage         — usage summary for caller's active key
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiblock.api.deps import AuthKey, DBSession
from aiblock.billing.metering import get_usage_summary
from aiblock.core.models import APIKey, User

router = APIRouter(prefix="/v1/keys", tags=["api-keys"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateKeyRequest(BaseModel):
    name: str = "Default"
    email: EmailStr  # used to look up / create the user


class KeyCreatedResponse(BaseModel):
    key_id: str
    raw_key: str   # shown ONCE — user must save this
    prefix: str
    name: str
    tier: str
    created_at: datetime
    warning: str = "Store this key securely — it will not be shown again."


class KeySummaryResponse(BaseModel):
    key_id: str
    prefix: str
    name: str
    tier: str
    is_active: bool
    requests_this_month: int
    created_at: datetime
    revoked_at: Optional[datetime] = None


class UsageResponse(BaseModel):
    tier: str
    requests_this_month: int
    monthly_limit: Optional[int]
    remaining: Optional[int]


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("", response_model=KeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_key(body: CreateKeyRequest, session: DBSession):
    """Create a new API key. No auth required — this is the bootstrap endpoint.

    In production, gate this behind email verification or OAuth.
    """
    # Find or create user
    stmt = select(User).where(User.email == body.email)
    user: User | None = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        user = User(email=body.email)
        session.add(user)
        await session.flush()

    raw_key, api_key = APIKey.generate()
    api_key.user_id = user.id
    api_key.name = body.name
    session.add(api_key)
    await session.commit()

    return KeyCreatedResponse(
        key_id=str(api_key.id),
        raw_key=raw_key,
        prefix=api_key.key_prefix,
        name=api_key.name,
        tier=api_key.tier,
        created_at=api_key.created_at,
    )


@router.get("", response_model=list[KeySummaryResponse])
async def list_keys(key: AuthKey, session: DBSession):
    """List all API keys for the authenticated user."""
    stmt = (
        select(APIKey)
        .where(APIKey.user_id == key.user_id)
        .order_by(APIKey.created_at.desc())
    )
    keys = (await session.execute(stmt)).scalars().all()

    return [
        KeySummaryResponse(
            key_id=str(k.id),
            prefix=k.key_prefix,
            name=k.name,
            tier=k.tier,
            is_active=k.is_active,
            requests_this_month=k.requests_this_month,
            created_at=k.created_at,
            revoked_at=k.revoked_at,
        )
        for k in keys
    ]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: str, key: AuthKey, session: DBSession):
    """Revoke an API key. Cannot be undone."""
    try:
        target_uuid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")

    target: APIKey | None = await session.get(APIKey, target_uuid)
    if target is None or target.user_id != key.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found.")

    target.revoked_at = datetime.now(timezone.utc)
    await session.commit()


@router.get("/usage", response_model=UsageResponse, tags=["usage"])
async def get_usage(key: AuthKey, session: DBSession):
    """Return usage statistics for the current API key."""
    summary = await get_usage_summary(key.id, session)
    return UsageResponse(**summary)
