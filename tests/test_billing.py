"""Tests for billing tiers and metering logic.

These tests do not require a real database — they test the pure-logic parts.
"""

import pytest

from aiblock.billing.tiers import FREE, PRO, ENTERPRISE, get_tier, TIER_MAP


class TestTiers:
    def test_free_tier_limits(self):
        assert FREE.monthly_limit == 10
        assert "wav2vec2" not in FREE.allowed_models
        assert "spectral" in FREE.allowed_models
        assert FREE.sync_allowed is False

    def test_pro_tier_allows_model(self):
        assert "wav2vec2" in PRO.allowed_models
        assert PRO.monthly_limit == 1_000
        assert PRO.sync_allowed is True

    def test_enterprise_unlimited(self):
        assert ENTERPRISE.monthly_limit is None
        assert ENTERPRISE.sync_allowed is True

    def test_get_tier_returns_correct_config(self):
        assert get_tier("free") is FREE
        assert get_tier("pro") is PRO
        assert get_tier("enterprise") is ENTERPRISE

    def test_get_tier_case_insensitive(self):
        assert get_tier("FREE") is FREE
        assert get_tier("Pro") is PRO

    def test_get_tier_unknown_raises(self):
        with pytest.raises(KeyError):
            get_tier("premium")

    def test_all_tiers_covered(self):
        for name in ("free", "pro", "enterprise"):
            tier = get_tier(name)
            assert tier.name == name
            assert tier.rate_limit_per_minute > 0


class TestAPIKeyGeneration:
    def test_generate_returns_raw_and_instance(self):
        from aiblock.core.models import APIKey
        raw, key = APIKey.generate()
        assert raw.startswith("abl_live_")
        assert len(raw) > 20
        assert key.key_hash is not None
        assert key.key_prefix == raw[:12]

    def test_generate_keys_are_unique(self):
        from aiblock.core.models import APIKey
        raw1, _ = APIKey.generate()
        raw2, _ = APIKey.generate()
        assert raw1 != raw2

    def test_hash_is_deterministic(self):
        from aiblock.core.models import APIKey
        raw = "abl_live_test_key_12345678"
        h1 = APIKey.hash_key(raw)
        h2 = APIKey.hash_key(raw)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_raw_key_not_stored(self):
        from aiblock.core.models import APIKey
        raw, key = APIKey.generate()
        # The raw key must not appear anywhere in the model instance
        assert raw not in str(key.__dict__)
