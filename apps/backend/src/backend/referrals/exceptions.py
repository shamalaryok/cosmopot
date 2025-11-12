"""Referral module exceptions."""


class ReferralError(Exception):
    """Base exception for referral module."""


class ReferralCodeNotFoundError(ReferralError):
    """Raised when a referral code is not found."""


class ReferralNotFoundError(ReferralError):
    """Raised when a referral is not found."""


class SelfReferralError(ReferralError):
    """Raised when trying to refer oneself."""


class WithdrawalInsufficientFundsError(ReferralError):
    """Raised when withdrawal amount exceeds available balance."""


class WithdrawalNotFoundError(ReferralError):
    """Raised when a withdrawal request is not found."""
