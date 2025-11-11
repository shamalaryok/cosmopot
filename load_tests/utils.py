"""Utility functions for load testing."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, UTC
from typing import Any

import structlog
from faker import Faker

fake = Faker()
logger = structlog.get_logger(__name__)


class AuthTokenGenerator:
    """Generates valid authentication tokens for test users."""

    def __init__(self, secret_key: str = "test-secret-key"):
        """Initialize token generator.

        Args:
            secret_key: Secret key for token generation
        """
        self.secret_key = secret_key

    def generate_jwt_token(self, user_id: str, email: str) -> str:
        """Generate a mock JWT token.

        Args:
            user_id: User ID
            email: User email

        Returns:
            Mock JWT token string
        """
        header = {"alg": "HS256", "typ": "JWT"}
        payload = {
            "sub": user_id,
            "email": email,
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        }

        import base64

        header_encoded = base64.urlsafe_b64encode(
            json.dumps(header).encode()
        ).decode().rstrip("=")
        payload_encoded = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip("=")

        signature = hmac.new(
            self.secret_key.encode(),
            f"{header_encoded}.{payload_encoded}".encode(),
            hashlib.sha256,
        ).digest()
        signature_encoded = (
            base64.urlsafe_b64encode(signature).decode().rstrip("=")
        )

        return f"{header_encoded}.{payload_encoded}.{signature_encoded}"


class TestDataGenerator:
    """Generates test data for API payloads."""

    @staticmethod
    def generate_email() -> str:
        """Generate a unique test email.

        Returns:
            Test email address
        """
        return f"loadtest_{fake.uuid4()}@test.local"

    @staticmethod
    def generate_password() -> str:
        """Generate a test password.

        Returns:
            Test password
        """
        return f"Test@{fake.password(length=12, special_chars=True)}"

    @staticmethod
    def generate_username() -> str:
        """Generate a unique test username.

        Returns:
            Test username
        """
        return f"user_{fake.word()}_{fake.random_int(min=1000, max=9999)}"

    @staticmethod
    def generate_generation_params() -> dict[str, Any]:
        """Generate parameters for generation API.

        Returns:
            Generation parameters
        """
        return {
            "prompt": fake.sentence(nb_words=10),
            "model": fake.random_element(["gpt-4", "gpt-3.5", "claude-3"]),
            "temperature": round(fake.pyfloat(min_value=0, max_value=2), 1),
            "max_tokens": fake.random_element([128, 256, 512, 1024]),
        }

    @staticmethod
    def generate_payment_params() -> dict[str, Any]:
        """Generate parameters for payment API.

        Returns:
            Payment parameters
        """
        return {
            "plan_id": fake.random_element(["starter", "pro", "enterprise"]),
            "amount": fake.random_element([9.99, 29.99, 99.99]),
            "currency": "USD",
        }


class MetricsCollector:
    """Collects and aggregates performance metrics."""

    def __init__(self):
        """Initialize metrics collector."""
        self.response_times: list[float] = []
        self.status_codes: dict[int, int] = {}
        self.errors: list[str] = []
        self.start_time = datetime.now(UTC)

    def record_response(self, response_time_ms: float, status_code: int) -> None:
        """Record a response.

        Args:
            response_time_ms: Response time in milliseconds
            status_code: HTTP status code
        """
        self.response_times.append(response_time_ms)
        self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1

    def record_error(self, error_message: str) -> None:
        """Record an error.

        Args:
            error_message: Error message
        """
        self.errors.append(error_message)

    def get_percentile(self, percentile: float) -> float:
        """Get response time percentile.

        Args:
            percentile: Percentile (e.g., 95 for p95)

        Returns:
            Response time at percentile in milliseconds
        """
        if not self.response_times:
            return 0
        sorted_times = sorted(self.response_times)
        index = int(len(sorted_times) * (percentile / 100))
        return sorted_times[min(index, len(sorted_times) - 1)]

    def get_summary(self) -> dict[str, Any]:
        """Get metrics summary.

        Returns:
            Dictionary with metrics
        """
        total_requests = len(self.response_times)
        total_errors = len(self.errors)
        success_rate = (
            (total_requests - total_errors) / total_requests * 100
            if total_requests > 0
            else 0
        )

        return {
            "total_requests": total_requests,
            "total_errors": total_errors,
            "success_rate": round(success_rate, 2),
            "error_rate": round(100 - success_rate, 2),
            "avg_response_time_ms": (
                round(sum(self.response_times) / len(self.response_times), 2)
                if self.response_times
                else 0
            ),
            "min_response_time_ms": (
                round(min(self.response_times), 2) if self.response_times else 0
            ),
            "max_response_time_ms": (
                round(max(self.response_times), 2) if self.response_times else 0
            ),
            "p50_response_time_ms": round(self.get_percentile(50), 2),
            "p95_response_time_ms": round(self.get_percentile(95), 2),
            "p99_response_time_ms": round(self.get_percentile(99), 2),
            "status_codes": self.status_codes,
            "test_duration_seconds": round(
                (datetime.now(UTC) - self.start_time).total_seconds(), 2
            ),
        }
