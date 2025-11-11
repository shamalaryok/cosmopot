from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth.models import User
from backend.payments.models import Payment, PaymentStatus
from backend.referrals.enums import ReferralTier, WithdrawalStatus
from backend.referrals.exceptions import (
    ReferralCodeNotFoundError,
    SelfReferralError,
    WithdrawalInsufficientFundsError,
)
from backend.referrals.models import Referral, ReferralEarning, ReferralWithdrawal
from backend.referrals.service import ReferralService, ReferralStats, WithdrawalRequest


@pytest.fixture
def referral_service() -> ReferralService:
    return ReferralService()


@pytest.fixture
async def test_users(async_session: AsyncSession) -> tuple[User, User, User]:
    """Create test users for referral testing."""
    user1 = User(
        email="referrer@example.com",
        hashed_password="hashed",
        is_active=True,
        is_verified=True,
    )
    user2 = User(
        email="referred@example.com", 
        hashed_password="hashed",
        is_active=True,
        is_verified=True,
    )
    user3 = User(
        email="tier2@example.com",
        hashed_password="hashed", 
        is_active=True,
        is_verified=True,
    )
    
    async_session.add_all([user1, user2, user3])
    await async_session.commit()
    for user in [user1, user2, user3]:
        await async_session.refresh(user)
    
    return user1, user2, user3


@pytest.fixture
async def test_payment(
    async_session: AsyncSession, test_users: tuple[User, User, User]
) -> Payment:
    """Create a test payment."""
    _, user2, _ = test_users
    payment = Payment(
        user_id=user2.id,
        subscription_id=1,
        provider_payment_id="test_payment_123",
        idempotency_key="test_key",
        status=PaymentStatus.SUCCEEDED,
        amount=Decimal("100.00"),
        currency="RUB",
    )
    
    async_session.add(payment)
    await async_session.commit()
    await async_session.refresh(payment)
    
    return payment


class TestReferralService:
    """Test cases for ReferralService."""

    async def test_get_referral_code_creates_new_code(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test that a new referral code is generated for a user without one."""
        user1, _, _ = test_users
        
        code = await referral_service.get_referral_code(async_session, user1)
        
        assert code is not None
        assert len(code) == 12
        assert code.isalnum()
        
        # Verify referral was created
        stmt = select(Referral).where(Referral.referrer_id == user1.id)
        referral = (await async_session.execute(stmt)).scalar_one_or_none()
        assert referral is not None
        assert referral.referral_code == code

    async def test_get_referral_code_returns_existing(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test that existing referral code is returned."""
        user1, _, _ = test_users
        
        # Create initial referral
        code1 = await referral_service.get_referral_code(async_session, user1)
        
        # Get code again
        code2 = await referral_service.get_referral_code(async_session, user1)
        
        assert code1 == code2

    async def test_get_referral_stats(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test referral statistics calculation."""
        user1, user2, user3 = test_users
        
        # Create referral relationship
        referral_code = await referral_service.get_referral_code(
            async_session, user1
        )
        await referral_service.create_referral(
            async_session, user1, user2, referral_code
        )
        await referral_service.create_referral(
            async_session, user1, user3, referral_code
        )
        
        # Create earnings
        earning1 = ReferralEarning(
            referral_id=user1.id,
            user_id=user1.id,
            payment_id=user1.id,
            amount=Decimal("20.00"),
            percentage=20,
            tier=ReferralTier.TIER1,
        )
        earning2 = ReferralEarning(
            referral_id=user1.id,
            user_id=user1.id,
            payment_id=user1.id,
            amount=Decimal("10.00"),
            percentage=10,
            tier=ReferralTier.TIER2,
        )
        
        # Create withdrawal
        withdrawal = ReferralWithdrawal(
            user_id=user1.id,
            amount=Decimal("5.00"),
            status=WithdrawalStatus.PROCESSED,
        )
        
        async_session.add_all([earning1, earning2, withdrawal])
        await async_session.commit()
        
        stats = await referral_service.get_referral_stats(async_session, user1)
        
        assert isinstance(stats, ReferralStats)
        assert stats.total_earnings == Decimal("30.00")
        assert stats.available_balance == Decimal("25.00")
        assert stats.total_withdrawn == Decimal("5.00")
        assert stats.tier1_count == 2
        assert stats.tier2_count == 0
        assert stats.pending_withdrawals == 0

    async def test_create_referral_success(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test successful referral creation."""
        user1, user2, _ = test_users
        referral_code = "TESTCODE123"
        
        referral = await referral_service.create_referral(
            async_session, user1, user2, referral_code
        )
        
        assert referral is not None
        assert referral.referrer_id == user1.id
        assert referral.referred_user_id == user2.id
        assert referral.referral_code == referral_code
        assert referral.tier == ReferralTier.TIER1

    async def test_create_referral_self_referral_fails(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test that self-referral raises an error."""
        user1, _, _ = test_users
        
        with pytest.raises(SelfReferralError):
            await referral_service.create_referral(
                async_session, user1, user1, "TESTCODE"
            )

    async def test_process_referral_code_success(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test successful referral code processing."""
        user1, user2, user3 = test_users
        
        # Create referral with placeholder user
        referral_code = await referral_service.get_referral_code(async_session, user1)
        
        # Process code for new user
        referral = await referral_service.process_referral_code(
            async_session, referral_code, user2
        )
        
        assert referral is not None
        assert referral.referred_user_id == user2.id

    async def test_process_referral_code_not_found(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test that invalid referral code raises error."""
        _, user2, _ = test_users
        
        with pytest.raises(ReferralCodeNotFoundError):
            await referral_service.process_referral_code(
                async_session, "INVALIDCODE", user2
            )

    async def test_create_earning_tier1_and_tier2(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
        test_payment: Payment,
    ) -> None:
        """Test that earnings are created for both tiers."""
        user1, user2, user3 = test_users
        
        # Create referral chain: user3 -> user1 -> user2
        referral_code1 = await referral_service.get_referral_code(
            async_session, user3
        )
        await referral_service.create_referral(
            async_session, user3, user1, referral_code1
        )
        
        referral_code2 = await referral_service.get_referral_code(
            async_session, user1
        )
        await referral_service.create_referral(
            async_session, user1, user2, referral_code2
        )
        
        # Create earnings for payment by user2
        earnings = await referral_service.create_earning(async_session, test_payment)
        
        assert len(earnings) == 2
        
        # Check tier1 earning (20%)
        tier1_earning = next(e for e in earnings if e.tier == ReferralTier.TIER1)
        assert tier1_earning.amount == Decimal("20.00")  # 20% of 100
        assert tier1_earning.percentage == 20
        assert tier1_earning.user_id == user1.id
        
        # Check tier2 earning (10%)
        tier2_earning = next(e for e in earnings if e.tier == ReferralTier.TIER2)
        assert tier2_earning.amount == Decimal("10.00")  # 10% of 100
        assert tier2_earning.percentage == 10
        assert tier2_earning.user_id == user3.id

    async def test_create_earning_no_referral(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_payment: Payment,
    ) -> None:
        """Test that no earnings are created when there's no referral."""
        earnings = await referral_service.create_earning(async_session, test_payment)
        assert len(earnings) == 0

    async def test_request_withdrawal_success(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test successful withdrawal request."""
        user1, _, _ = test_users
        
        # Create earning
        earning = ReferralEarning(
            referral_id=user1.id,
            user_id=user1.id,
            payment_id=user1.id,
            amount=Decimal("50.00"),
            percentage=20,
            tier=ReferralTier.TIER1,
        )
        async_session.add(earning)
        await async_session.commit()
        
        request = WithdrawalRequest(amount=Decimal("25.00"))
        withdrawal = await referral_service.request_withdrawal(
            async_session, user1, request
        )
        
        assert withdrawal is not None
        assert withdrawal.user_id == user1.id
        assert withdrawal.amount == Decimal("25.00")
        assert withdrawal.status == WithdrawalStatus.PENDING

    async def test_request_withdrawal_insufficient_funds(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test that withdrawal fails with insufficient funds."""
        user1, _, _ = test_users
        
        request = WithdrawalRequest(amount=Decimal("100.00"))
        
        with pytest.raises(WithdrawalInsufficientFundsError):
            await referral_service.request_withdrawal(async_session, user1, request)

    async def test_get_user_withdrawals(
        self,
        async_session: AsyncSession,
        referral_service: ReferralService,
        test_users: tuple[User, User, User],
    ) -> None:
        """Test getting user withdrawal history."""
        user1, _, _ = test_users
        
        # Create withdrawals
        withdrawal1 = ReferralWithdrawal(
            user_id=user1.id,
            amount=Decimal("10.00"),
            status=WithdrawalStatus.PROCESSED,
        )
        withdrawal2 = ReferralWithdrawal(
            user_id=user1.id,
            amount=Decimal("20.00"),
            status=WithdrawalStatus.PENDING,
        )
        
        async_session.add_all([withdrawal1, withdrawal2])
        await async_session.commit()
        
        withdrawals = await referral_service.get_user_withdrawals(async_session, user1)
        
        assert len(withdrawals) == 2
        # Should be ordered by created_at desc
        assert withdrawals[0].amount == Decimal("20.00")
        assert withdrawals[1].amount == Decimal("10.00")