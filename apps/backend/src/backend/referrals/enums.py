from enum import StrEnum


class ReferralTier(StrEnum):
    """Referral tier levels."""

    TIER1 = "tier1"  # Direct referrals - 20%
    TIER2 = "tier2"  # Indirect referrals - 10%


class WithdrawalStatus(StrEnum):
    """Withdrawal request status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"
