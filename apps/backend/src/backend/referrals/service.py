from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, cast

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.payments.models import Payment
from backend.referrals.enums import ReferralTier, WithdrawalStatus
from backend.referrals.exceptions import (
    ReferralCodeNotFoundError,
    SelfReferralError,
    WithdrawalInsufficientFundsError,
)
from backend.referrals.models import Referral, ReferralEarning, ReferralWithdrawal


class UserProtocol(Protocol):
    """Protocol for user models used in referral operations."""

    @property
    def id(self) -> int | uuid.UUID:
        """Unique identifier for the user."""
        ...


@dataclass(slots=True)
class ReferralStats:
    """Referral statistics for a user."""
    referral_code: str
    total_earnings: Decimal
    available_balance: Decimal
    total_withdrawn: Decimal
    tier1_count: int
    tier2_count: int
    pending_withdrawals: int


@dataclass(slots=True)
class WithdrawalRequest:
    """Withdrawal request data."""
    amount: Decimal
    notes: str | None = None


class ReferralService:
    """Service for managing referrals and earnings."""

    def __init__(self) -> None:
        self._logger = structlog.get_logger(__name__)

    async def get_referral_code(self, session: AsyncSession, user: UserProtocol) -> str:
        """Get or generate referral code for a user."""
        stmt = (
            select(Referral.referral_code).where(
                Referral.referrer_id == cast(uuid.UUID, user.id)
            ).limit(1)
        )
        result = await session.execute(stmt)
        existing_code = result.scalar_one_or_none()
        
        if existing_code:
            return existing_code
            
        code = await self._generate_referral_code(session, user)
        
        # Create a referral record for the code (placeholder with self as referred_user)
        referral = Referral(
            referrer_id=cast(uuid.UUID, user.id),
            # Temporary, updated during actual referral
            referred_user_id=cast(uuid.UUID, user.id),
            referral_code=code,
            tier=ReferralTier.TIER1,
        )
        session.add(referral)
        await session.flush()
        
        return code

    async def get_referral_stats(
        self, session: AsyncSession, user: UserProtocol
    ) -> ReferralStats:
        """Get referral statistics for a user."""
        referral_code = await self.get_referral_code(session, user)
        
        # Get total earnings
        earnings_stmt = (
            select(func.coalesce(func.sum(ReferralEarning.amount), Decimal("0")))
            .where(ReferralEarning.user_id == cast(uuid.UUID, user.id))
        )
        total_earnings = (await session.execute(earnings_stmt)).scalar() or Decimal("0")
        
        # Get total withdrawn
        withdrawals_stmt = (
            select(func.coalesce(func.sum(ReferralWithdrawal.amount), Decimal("0")))
            .where(
                ReferralWithdrawal.user_id == cast(uuid.UUID, user.id),
                ReferralWithdrawal.status == WithdrawalStatus.PROCESSED
            )
        )
        total_withdrawn = (
            await session.execute(withdrawals_stmt)
        ).scalar() or Decimal("0")
        
        # Get pending withdrawals
        pending_stmt = select(func.count(ReferralWithdrawal.id)).where(
            ReferralWithdrawal.user_id == cast(uuid.UUID, user.id),
            ReferralWithdrawal.status == WithdrawalStatus.PENDING
        )
        pending_withdrawals = (await session.execute(pending_stmt)).scalar() or 0
        
        available_balance = total_earnings - total_withdrawn
        
        # Get referral counts by tier
        tier1_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_id == cast(uuid.UUID, user.id),
            Referral.tier == ReferralTier.TIER1
        )
        tier1_count = (await session.execute(tier1_stmt)).scalar() or 0
        
        tier2_stmt = select(func.count(Referral.id)).where(
            Referral.referrer_id == cast(uuid.UUID, user.id),
            Referral.tier == ReferralTier.TIER2
        )
        tier2_count = (await session.execute(tier2_stmt)).scalar() or 0
        
        return ReferralStats(
            referral_code=referral_code,
            total_earnings=total_earnings.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            available_balance=available_balance.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            total_withdrawn=total_withdrawn.quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            tier1_count=tier1_count,
            tier2_count=tier2_count,
            pending_withdrawals=pending_withdrawals,
        )

    async def create_referral(
        self,
        session: AsyncSession,
        referrer: UserProtocol,
        referred_user: UserProtocol,
        referral_code: str,
    ) -> Referral:
        """Create a referral relationship."""
        if referrer.id == referred_user.id:
            raise SelfReferralError("Cannot refer yourself")
            
        # Check if referral already exists
        existing_stmt = select(Referral).where(
            Referral.referrer_id == cast(uuid.UUID, referrer.id),
            Referral.referred_user_id == cast(uuid.UUID, referred_user.id)
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            return existing
            
        referral = Referral(
            referrer_id=cast(uuid.UUID, referrer.id),
            referred_user_id=cast(uuid.UUID, referred_user.id),
            referral_code=referral_code,
            tier=ReferralTier.TIER1,
        )
        session.add(referral)
        await session.flush()
        return referral

    async def process_referral_code(
        self, session: AsyncSession, referral_code: str, user: UserProtocol
    ) -> Referral | None:
        """Process a referral code during user registration."""
        stmt = select(Referral).where(
            Referral.referral_code == referral_code,
            Referral.is_active
        )
        referral = (await session.execute(stmt)).scalar_one_or_none()
        
        if not referral:
            raise ReferralCodeNotFoundError(
                f"Referral code '{referral_code}' not found"
            )
            
        if referral.referred_user_id:
            # This referral code has already been used
            return None
            
        # Update the referral with the new user
        referral.referred_user_id = cast(uuid.UUID, user.id)
        await session.flush()
        
        # Create tier2 referrals for the referrer's referrer (if exists)
        await self._create_tier2_referral(
            session,
            referral.referrer_id,
            cast(uuid.UUID, user.id),
        )
        
        return referral

    async def create_earning(
        self, session: AsyncSession, payment: Payment
    ) -> list[ReferralEarning]:
        """Create referral earnings for a successful payment."""
        earnings: list[ReferralEarning] = []
        
        # Find the referral relationship for the paying user
        referral_stmt = select(Referral).where(
            Referral.referred_user_id == cast(uuid.UUID, payment.user_id),
            Referral.is_active
        )
        referral = (await session.execute(referral_stmt)).scalar_one_or_none()
        
        if not referral:
            return earnings
            
        # Calculate tier1 earnings (20%)
        tier1_percentage = 20
        tier1_amount = (
            payment.amount * Decimal(tier1_percentage) / Decimal("100")
        ).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        
        tier1_earning = ReferralEarning(
            referral_id=referral.id,
            user_id=referral.referrer_id,
            payment_id=payment.id,
            amount=tier1_amount,
            percentage=tier1_percentage,
            tier=ReferralTier.TIER1,
        )
        earnings.append(tier1_earning)
        
        # Find tier2 referral (referrer's referrer)
        tier2_referral_stmt = select(Referral).where(
            Referral.referred_user_id == referral.referrer_id,
            Referral.tier == ReferralTier.TIER1,
            Referral.is_active
        )
        tier2_referral = (
            await session.execute(tier2_referral_stmt)
        ).scalar_one_or_none()
        
        if tier2_referral:
            # Calculate tier2 earnings (10%)
            tier2_percentage = 10
            tier2_amount = (
                payment.amount * Decimal(tier2_percentage) / Decimal("100")
            ).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            
            tier2_earning = ReferralEarning(
                referral_id=referral.id,  # Link to the original referral
                user_id=tier2_referral.referrer_id,
                payment_id=payment.id,
                amount=tier2_amount,
                percentage=tier2_percentage,
                tier=ReferralTier.TIER2,
            )
            earnings.append(tier2_earning)
            
        for earning in earnings:
            session.add(earning)
            
        await session.flush()
        return earnings

    async def request_withdrawal(
        self, session: AsyncSession, user: UserProtocol, request: WithdrawalRequest
    ) -> ReferralWithdrawal:
        """Request a withdrawal of referral earnings."""
        # Check available balance
        stats = await self.get_referral_stats(session, user)
        if request.amount > stats.available_balance:
            raise WithdrawalInsufficientFundsError(
                f"Insufficient balance. Available: {stats.available_balance}, "
                f"Requested: {request.amount}"
            )
            
        withdrawal = ReferralWithdrawal(
            user_id=cast(uuid.UUID, user.id),
            amount=request.amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            status=WithdrawalStatus.PENDING,
            notes=request.notes,
        )
        session.add(withdrawal)
        await session.flush()
        return withdrawal

    async def get_user_withdrawals(
        self, session: AsyncSession, user: UserProtocol
    ) -> list[ReferralWithdrawal]:
        """Get all withdrawal requests for a user."""
        stmt = select(ReferralWithdrawal).where(
            ReferralWithdrawal.user_id == cast(uuid.UUID, user.id)
        ).order_by(ReferralWithdrawal.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _generate_referral_code(
        self,
        session: AsyncSession,
        user: UserProtocol,
    ) -> str:
        """Generate a unique referral code for a user."""
        for _ in range(10):  # Try up to 10 times
            code = secrets.token_urlsafe(8)[:12].upper()

            # Check if code already exists
            existing_stmt = (
                select(Referral.id).where(Referral.referral_code == code).limit(1)
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            
            if not existing:
                return code
                
        raise RuntimeError("Failed to generate unique referral code")

    async def _create_tier2_referral(
        self, session: AsyncSession, referrer_id: uuid.UUID, referred_user_id: uuid.UUID
    ) -> None:
        """Create tier2 referral relationship for the referrer's referrer."""
        # Find the referrer's referrer
        referrer_referral_stmt = select(Referral).where(
            Referral.referred_user_id == referrer_id,
            Referral.tier == ReferralTier.TIER1,
            Referral.is_active
        )
        referrer_referral = (
            await session.execute(referrer_referral_stmt)
        ).scalar_one_or_none()
        
        if not referrer_referral:
            return
            
        # Check if tier2 referral already exists
        existing_stmt = select(Referral).where(
            Referral.referrer_id == referrer_referral.referrer_id,
            Referral.referred_user_id == referred_user_id,
            Referral.tier == ReferralTier.TIER2
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            return
            
        tier2_referral = Referral(
            referrer_id=referrer_referral.referrer_id,
            referred_user_id=referred_user_id,
            referral_code=referrer_referral.referral_code,  # Use same code
            tier=ReferralTier.TIER2,
        )
        session.add(tier2_referral)