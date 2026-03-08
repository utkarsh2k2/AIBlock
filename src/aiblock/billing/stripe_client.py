"""Stripe integration for subscription management.

Supports:
  - Creating a Stripe Customer when a user registers
  - Creating checkout sessions for Pro / Enterprise upgrades
  - Handling webhook events to sync subscription state to the DB
"""

from typing import Optional

from aiblock.settings import get_settings


def _stripe():
    try:
        import stripe
    except ImportError as e:
        raise ImportError("stripe is required: pip install stripe") from e
    settings = get_settings()
    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_customer(email: str) -> str:
    """Create a Stripe Customer and return the customer ID."""
    stripe = _stripe()
    customer = stripe.Customer.create(email=email)
    return customer.id


def create_checkout_session(
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout Session. Returns the checkout URL."""
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def create_portal_session(customer_id: str, return_url: str) -> str:
    """Create a Stripe Customer Portal session. Returns the portal URL."""
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


def construct_webhook_event(payload: bytes, sig_header: str):
    """Verify and parse a Stripe webhook event. Raises on invalid signature."""
    stripe = _stripe()
    settings = get_settings()
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )


def get_subscription_tier(subscription_id: str) -> str:
    """Return 'pro' or 'enterprise' based on the active subscription's price ID."""
    stripe = _stripe()
    settings = get_settings()
    sub = stripe.Subscription.retrieve(subscription_id)
    price_id = sub["items"]["data"][0]["price"]["id"]
    if price_id == settings.stripe_enterprise_price_id:
        return "enterprise"
    return "pro"


def cancel_subscription(subscription_id: str) -> None:
    """Cancel a Stripe subscription at period end."""
    stripe = _stripe()
    stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
