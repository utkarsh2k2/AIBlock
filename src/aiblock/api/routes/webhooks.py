"""Stripe webhook handler.

Listens for subscription events and syncs tier state to the DB.

Register this URL in the Stripe dashboard:
  https://your-domain.com/v1/webhooks/stripe
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aiblock.api.deps import DBSession
from aiblock.billing.stripe_client import construct_webhook_event, get_subscription_tier
from aiblock.core.models import APIKey, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.post("/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    session: DBSession,
    stripe_signature: str = Header(alias="Stripe-Signature"),
):
    payload = await request.body()

    try:
        event = construct_webhook_event(payload, stripe_signature)
    except Exception as exc:
        log.warning("Invalid Stripe signature: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature.")

    event_type = event["type"]
    log.info("Stripe event: %s", event_type)

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        await _handle_subscription_change(event["data"]["object"], session, active=True)

    elif event_type in ("customer.subscription.deleted",):
        await _handle_subscription_change(event["data"]["object"], session, active=False)

    return {"received": True}


async def _handle_subscription_change(subscription: dict, session: AsyncSession, active: bool) -> None:
    customer_id: str = subscription["customer"]
    subscription_id: str = subscription["id"]

    stmt = select(User).where(User.stripe_customer_id == customer_id)
    user: User | None = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        log.warning("No user found for Stripe customer %s", customer_id)
        return

    if active:
        new_tier = get_subscription_tier(subscription_id)
        user.tier = new_tier
        user.stripe_subscription_id = subscription_id
        # Sync tier to all active API keys for this user
        keys_stmt = select(APIKey).where(
            APIKey.user_id == user.id,
            APIKey.revoked_at.is_(None),
        )
        keys = (await session.execute(keys_stmt)).scalars().all()
        for k in keys:
            k.tier = new_tier
    else:
        # Subscription cancelled — downgrade to free
        user.tier = "free"
        user.stripe_subscription_id = None
        keys_stmt = select(APIKey).where(
            APIKey.user_id == user.id,
            APIKey.revoked_at.is_(None),
        )
        keys = (await session.execute(keys_stmt)).scalars().all()
        for k in keys:
            k.tier = "free"

    await session.commit()
    log.info("Updated user %s to tier=%s", user.email, user.tier)
