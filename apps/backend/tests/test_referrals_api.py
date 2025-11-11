from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.dependencies.users import get_current_user
from backend.app import create_app
from backend.auth.dependencies import get_rate_limiter
from backend.auth.models import User
from backend.db.dependencies import get_db_session
from backend.referrals.enums import ReferralTier, WithdrawalStatus
from backend.referrals.models import Referral, ReferralEarning, ReferralWithdrawal


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
async def authenticated_client(
    client: TestClient,
    async_session,
    mock_user,
) -> AsyncIterator[TestClient]:
    """Create authenticated test client."""
    app = client.app
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db_session] = lambda: async_session
    app.dependency_overrides[get_rate_limiter] = lambda: AsyncMock()

    yield client

    app.dependency_overrides.clear()


class TestReferralAPI:
    """Test cases for referral API endpoints."""

    async def test_get_referral_code(
        self,
        authenticated_client: TestClient,
        async_session,
        mock_user,
    ) -> None:
        """Test GET /api/v1/referrals/code endpoint."""
        response = authenticated_client.get("/api/v1/referrals/code")

        assert response.status_code == 200
        data = response.json()
        assert "referral_code" in data
        assert "referral_url" in data
        assert len(data["referral_code"]) == 12
        assert mock_user.email not in data["referral_url"]

    async def test_get_referral_stats(
        self,
        authenticated_client: TestClient,
        async_session,
        mock_user,
    ) -> None:
        """Test GET /api/v1/referrals/stats endpoint."""
        earning = ReferralEarning(
            referral_id=mock_user.id,
            user_id=mock_user.id,
            payment_id=mock_user.id,
            amount=Decimal("20.00"),
            percentage=20,
            tier=ReferralTier.TIER1,
        )
        withdrawal = ReferralWithdrawal(
            user_id=mock_user.id,
            amount=Decimal("5.00"),
            status=WithdrawalStatus.PROCESSED,
        )

        async_session.add_all([earning, withdrawal])
        await async_session.commit()

        response = authenticated_client.get("/api/v1/referrals/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_earnings"] == "20.00"
        assert data["available_balance"] == "15.00"
        assert data["total_withdrawn"] == "5.00"
        assert data["tier1_count"] == 0
        assert data["tier2_count"] == 0
        assert data["pending_withdrawals"] == 0

    async def test_request_withdrawal_success(
        self,
        authenticated_client: TestClient,
        async_session,
        mock_user,
    ) -> None:
        """Test POST /api/v1/referrals/withdraw endpoint success."""
        earning = ReferralEarning(
            referral_id=mock_user.id,
            user_id=mock_user.id,
            payment_id=mock_user.id,
            amount=Decimal("50.00"),
            percentage=20,
            tier=ReferralTier.TIER1,
        )
        async_session.add(earning)
        await async_session.commit()

        withdrawal_data = {"amount": "25.00", "notes": "Test withdrawal"}

        response = authenticated_client.post(
            "/api/v1/referrals/withdraw",
            json=withdrawal_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["amount"] == "25.00"
        assert data["status"] == "pending"
        assert data["notes"] == "Test withdrawal"
        assert "id" in data
        assert "created_at" in data

    async def test_request_withdrawal_insufficient_funds(
        self,
        authenticated_client: TestClient,
        mock_user,
    ) -> None:
        """Test POST /api/v1/referrals/withdraw endpoint with insufficient funds."""
        withdrawal_data = {"amount": "100.00", "notes": "Test withdrawal"}

        response = authenticated_client.post(
            "/api/v1/referrals/withdraw",
            json=withdrawal_data,
        )

        assert response.status_code == 400
        assert "Insufficient balance" in response.json()["detail"]

    async def test_request_withdrawal_invalid_amount(
        self,
        authenticated_client: TestClient,
        mock_user,
    ) -> None:
        """Test POST /api/v1/referrals/withdraw endpoint with invalid amount."""
        withdrawal_data = {"amount": "-10.00", "notes": "Test withdrawal"}

        response = authenticated_client.post(
            "/api/v1/referrals/withdraw",
            json=withdrawal_data,
        )

        assert response.status_code == 422

    async def test_get_withdrawals(
        self,
        authenticated_client: TestClient,
        async_session,
        mock_user,
    ) -> None:
        """Test GET /api/v1/referrals/withdrawals endpoint."""
        withdrawal1 = ReferralWithdrawal(
            user_id=mock_user.id,
            amount=Decimal("10.00"),
            status=WithdrawalStatus.PROCESSED,
        )
        withdrawal2 = ReferralWithdrawal(
            user_id=mock_user.id,
            amount=Decimal("20.00"),
            status=WithdrawalStatus.PENDING,
        )

        async_session.add_all([withdrawal1, withdrawal2])
        await async_session.commit()

        response = authenticated_client.get("/api/v1/referrals/withdrawals")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["pending_count"] == 1
        assert len(data["withdrawals"]) == 2

        withdrawals = data["withdrawals"]
        assert withdrawals[0]["amount"] == "20.00"
        assert withdrawals[1]["amount"] == "10.00"

    async def test_get_withdrawals_pagination(
        self,
        authenticated_client: TestClient,
        async_session,
        mock_user,
    ) -> None:
        """Test GET /api/v1/referrals/withdrawals endpoint with pagination."""
        withdrawals = [
            ReferralWithdrawal(
                user_id=mock_user.id,
                amount=Decimal(f"{index}.00"),
                status=WithdrawalStatus.PENDING,
            )
            for index in range(1, 6)
        ]

        async_session.add_all(withdrawals)
        await async_session.commit()

        response = authenticated_client.get(
            "/api/v1/referrals/withdrawals",
            params={"limit": 2, "offset": 1},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["withdrawals"]) == 2

    async def test_apply_referral_code_success(
        self,
        authenticated_client: TestClient,
        async_session,
        mock_user,
    ) -> None:
        """Test POST /api/v1/referrals/apply/{referral_code} endpoint success."""
        referrer = User(
            email="referrer@example.com",
            hashed_password="hashed",
            is_active=True,
            is_verified=True,
        )
        async_session.add(referrer)
        await async_session.commit()
        await async_session.refresh(referrer)

        referral = Referral(
            referrer_id=referrer.id,
            referred_user_id=referrer.id,
            referral_code="TESTCODE123",
            tier=ReferralTier.TIER1,
        )
        async_session.add(referral)
        await async_session.commit()

        response = authenticated_client.post("/api/v1/referrals/apply/TESTCODE123")

        assert response.status_code == 204

    async def test_apply_referral_code_not_found(
        self,
        authenticated_client: TestClient,
    ) -> None:
        """Test applying an invalid referral code returns 404."""
        response = authenticated_client.post("/api/v1/referrals/apply/INVALIDCODE")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
