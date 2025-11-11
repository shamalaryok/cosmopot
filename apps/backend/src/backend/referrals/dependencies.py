from __future__ import annotations

from backend.referrals.service import ReferralService

__all__ = ["get_referral_service"]


def get_referral_service() -> ReferralService:
    """Get referral service instance."""
    return ReferralService()