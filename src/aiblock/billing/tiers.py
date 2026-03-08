"""Plan definitions — limits and capabilities per tier.

Changing a tier's limits here propagates everywhere automatically.
The enforcement logic lives in metering.py; this module is data-only.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TierConfig:
    name: str
    monthly_limit: Optional[int]    # None = unlimited
    allowed_models: frozenset[str]
    sync_allowed: bool              # can use the synchronous /detect endpoint
    rate_limit_per_minute: int      # requests per minute per API key
    cache_hits_count: bool          # whether cache hits count toward monthly limit
    price_monthly_usd: Optional[float]  # None = contact sales


FREE = TierConfig(
    name="free",
    monthly_limit=10,
    allowed_models=frozenset(["spectral"]),
    sync_allowed=False,
    rate_limit_per_minute=5,
    cache_hits_count=False,   # free users benefit from caching
    price_monthly_usd=0.0,
)

PRO = TierConfig(
    name="pro",
    monthly_limit=1_000,
    allowed_models=frozenset(["spectral", "wav2vec2"]),
    sync_allowed=True,
    rate_limit_per_minute=60,
    cache_hits_count=False,
    price_monthly_usd=29.0,
)

ENTERPRISE = TierConfig(
    name="enterprise",
    monthly_limit=None,           # unlimited
    allowed_models=frozenset(["spectral", "wav2vec2"]),
    sync_allowed=True,
    rate_limit_per_minute=600,
    cache_hits_count=False,
    price_monthly_usd=None,       # contact sales
)

TIER_MAP: dict[str, TierConfig] = {
    "free": FREE,
    "pro": PRO,
    "enterprise": ENTERPRISE,
}


def get_tier(name: str) -> TierConfig:
    """Return TierConfig for the given tier name. Raises KeyError on unknown tier."""
    return TIER_MAP[name.lower()]
