from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ReferralCodeResponse(BaseModel):
    """Response model for referral code endpoint."""
    referral_code: str = Field(..., description="User's unique referral code")
    referral_url: str = Field(..., description="Full referral URL")


class ReferralStatsResponse(BaseModel):
    """Response model for referral statistics endpoint."""
    referral_code: str = Field(..., description="User's unique referral code")
    total_earnings: Decimal = Field(
        ...,
        description="Total earnings from referrals",
    )
    available_balance: Decimal = Field(
        ...,
        description="Available balance for withdrawal",
    )
    total_withdrawn: Decimal = Field(
        ...,
        description="Total amount withdrawn",
    )
    tier1_count: int = Field(..., description="Number of tier1 referrals")
    tier2_count: int = Field(..., description="Number of tier2 referrals")
    pending_withdrawals: int = Field(
        ...,
        description="Number of pending withdrawal requests",
    )

    @field_validator(
        "total_earnings",
        "available_balance",
        "total_withdrawn",
        mode="before",
    )
    @classmethod
    def validate_decimal_fields(cls, v: Any) -> Decimal:
        """Validate decimal fields."""
        if isinstance(v, str):
            return Decimal(v)
        return v


class WithdrawalRequest(BaseModel):
    """Request model for withdrawal endpoint."""
    amount: Decimal = Field(..., gt=0, description="Amount to withdraw")
    notes: str | None = Field(
        None,
        max_length=500,
        description="Optional notes for the withdrawal",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: Any) -> Decimal:
        """Validate amount field."""
        if isinstance(v, str):
            return Decimal(v)
        return v


class WithdrawalResponse(BaseModel):
    """Response model for withdrawal endpoint."""
    id: str = Field(..., description="Withdrawal request ID")
    amount: Decimal = Field(..., description="Withdrawal amount")
    status: str = Field(..., description="Withdrawal status")
    created_at: str = Field(..., description="Creation timestamp")
    notes: str | None = Field(None, description="Withdrawal notes")
    processed_at: str | None = Field(None, description="Processing timestamp")

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v: Any) -> Decimal:
        """Validate amount field."""
        if isinstance(v, str):
            return Decimal(v)
        return v


class WithdrawalListResponse(BaseModel):
    """Response model for withdrawal list endpoint."""
    withdrawals: list[WithdrawalResponse] = Field(
        ...,
        description="List of withdrawal requests",
    )
    total: int = Field(..., description="Total number of withdrawals")
    pending_count: int = Field(..., description="Number of pending withdrawals")