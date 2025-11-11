"""Tests for load testing utilities."""

from __future__ import annotations

import pytest

from load_tests.utils import (
    AuthTokenGenerator,
    MetricsCollector,
    TestDataGenerator,
)


class TestAuthTokenGenerator:
    """Tests for AuthTokenGenerator."""

    def test_generate_jwt_token(self) -> None:
        """Test JWT token generation."""
        generator = AuthTokenGenerator()
        token = generator.generate_jwt_token("user-123", "user@example.com")

        assert token is not None
        assert len(token) > 0
        assert token.count(".") == 2  # JWT format: header.payload.signature

    def test_token_has_valid_format(self) -> None:
        """Test generated token has valid JWT format."""
        generator = AuthTokenGenerator()
        token = generator.generate_jwt_token("user-456", "test@example.com")

        parts = token.split(".")
        assert len(parts) == 3
        assert all(part for part in parts)  # No empty parts


class TestTestDataGenerator:
    """Tests for TestDataGenerator."""

    def test_generate_email(self) -> None:
        """Test email generation."""
        email = TestDataGenerator.generate_email()

        assert "@" in email
        assert ".local" in email
        assert "loadtest" in email

    def test_emails_are_unique(self) -> None:
        """Test generated emails are unique."""
        emails = [TestDataGenerator.generate_email() for _ in range(10)]

        assert len(emails) == len(set(emails))

    def test_generate_password(self) -> None:
        """Test password generation."""
        password = TestDataGenerator.generate_password()

        assert len(password) > 8
        assert any(c.isupper() for c in password)

    def test_generate_username(self) -> None:
        """Test username generation."""
        username = TestDataGenerator.generate_username()

        assert "user_" in username
        assert len(username) > 5

    def test_usernames_are_unique(self) -> None:
        """Test generated usernames are unique."""
        usernames = [TestDataGenerator.generate_username() for _ in range(10)]

        assert len(usernames) == len(set(usernames))

    def test_generate_generation_params(self) -> None:
        """Test generation parameters generation."""
        params = TestDataGenerator.generate_generation_params()

        assert "prompt" in params
        assert "model" in params
        assert "temperature" in params
        assert "max_tokens" in params

        assert isinstance(params["prompt"], str)
        assert params["model"] in ["gpt-4", "gpt-3.5", "claude-3"]
        assert 0 <= params["temperature"] <= 2
        assert params["max_tokens"] in [128, 256, 512, 1024]

    def test_generate_payment_params(self) -> None:
        """Test payment parameters generation."""
        params = TestDataGenerator.generate_payment_params()

        assert "plan_id" in params
        assert "amount" in params
        assert "currency" in params

        assert params["plan_id"] in ["starter", "pro", "enterprise"]
        assert params["amount"] in [9.99, 29.99, 99.99]
        assert params["currency"] == "USD"


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_record_response(self) -> None:
        """Test recording responses."""
        collector = MetricsCollector()

        collector.record_response(100.0, 200)
        collector.record_response(150.0, 200)
        collector.record_response(200.0, 201)

        assert len(collector.response_times) == 3
        assert 200 in collector.status_codes
        assert collector.status_codes[200] == 2
        assert collector.status_codes[201] == 1

    def test_record_error(self) -> None:
        """Test recording errors."""
        collector = MetricsCollector()

        collector.record_error("Connection timeout")
        collector.record_error("Invalid response")

        assert len(collector.errors) == 2

    def test_get_percentile(self) -> None:
        """Test percentile calculation."""
        collector = MetricsCollector()

        for i in range(1, 101):
            collector.record_response(float(i), 200)

        p50 = collector.get_percentile(50)
        p95 = collector.get_percentile(95)
        p99 = collector.get_percentile(99)

        assert 45 <= p50 <= 55
        assert 90 <= p95 <= 100
        assert 95 <= p99 <= 100

    def test_get_summary(self) -> None:
        """Test summary generation."""
        collector = MetricsCollector()

        # Record some responses and errors
        for i in range(100):
            collector.record_response(100.0 + i, 200)

        collector.record_error("Test error")

        summary = collector.get_summary()

        assert "total_requests" in summary
        assert "total_errors" in summary
        assert "success_rate" in summary
        assert "error_rate" in summary
        assert "avg_response_time_ms" in summary
        assert "min_response_time_ms" in summary
        assert "max_response_time_ms" in summary
        assert "p50_response_time_ms" in summary
        assert "p95_response_time_ms" in summary
        assert "p99_response_time_ms" in summary
        assert "status_codes" in summary

        assert summary["total_requests"] == 100
        assert summary["total_errors"] == 1
        assert summary["success_rate"] == 99.0
        assert summary["error_rate"] == 1.0

    def test_empty_metrics_summary(self) -> None:
        """Test summary with no data."""
        collector = MetricsCollector()
        summary = collector.get_summary()

        assert summary["total_requests"] == 0
        assert summary["total_errors"] == 0
        assert summary["success_rate"] == 0
        assert summary["avg_response_time_ms"] == 0

    def test_metrics_with_various_status_codes(self) -> None:
        """Test metrics collection with various status codes."""
        collector = MetricsCollector()

        collector.record_response(100.0, 200)
        collector.record_response(150.0, 201)
        collector.record_response(200.0, 400)
        collector.record_response(250.0, 500)

        summary = collector.get_summary()

        assert summary["total_requests"] == 4
        assert 200 in summary["status_codes"]
        assert 201 in summary["status_codes"]
        assert 400 in summary["status_codes"]
        assert 500 in summary["status_codes"]
