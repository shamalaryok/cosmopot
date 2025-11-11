"""Integration tests for the referral module."""

from __future__ import annotations

import uuid

import pytest

from backend.referrals.enums import ReferralTier, WithdrawalStatus
from backend.referrals.exceptions import ReferralError
from backend.referrals.models import Referral
from backend.referrals.service import ReferralService


def test_referral_service_instantiation() -> None:
    """ReferralService can be instantiated without dependencies."""
    service = ReferralService()
    assert isinstance(service, ReferralService)


def test_referral_enums_values() -> None:
    """Referral enums expose the expected values."""
    assert ReferralTier.TIER1.value == "tier1"
    assert ReferralTier.TIER2.value == "tier2"
    assert WithdrawalStatus.PENDING.value == "pending"


def test_referral_model_creation() -> None:
    """Referral model can be instantiated with core fields."""
    referral = Referral(
        referrer_id=uuid.uuid4(),
        referred_user_id=uuid.uuid4(),
        referral_code="TESTCODE123",
        tier=ReferralTier.TIER1,
    )

    assert referral.referral_code == "TESTCODE123"
    assert referral.tier is ReferralTier.TIER1
    assert referral.is_active is True


def test_referral_error_string_representation() -> None:
    """ReferralError preserves the provided message."""
    with pytest.raises(ReferralError, match="Test error"):
        raise ReferralError("Test error")
