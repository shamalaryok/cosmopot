"""Load testing configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv(".env.load-testing")


@dataclass
class LoadTestConfig:
    """Load testing configuration."""

    # API Configuration
    host: str = os.getenv("LOAD_TEST_HOST", "http://localhost:8000")
    timeout: int = int(os.getenv("LOAD_TEST_TIMEOUT", "30"))

    # Load Testing Parameters
    users_min: int = int(os.getenv("LOAD_TEST_USERS_MIN", "100"))
    users_max: int = int(os.getenv("LOAD_TEST_USERS_MAX", "1000"))
    spawn_rate: int = int(os.getenv("LOAD_TEST_SPAWN_RATE", "10"))
    duration_seconds: int = int(os.getenv("LOAD_TEST_DURATION_SECONDS", "300"))

    # Generation API Parameters
    generation_requests_per_second: int = int(
        os.getenv("GENERATION_REQUESTS_PER_SECOND", "10")
    )
    generation_success_rate_threshold: float = float(
        os.getenv("GENERATION_SUCCESS_RATE_THRESHOLD", "0.95")
    )
    generation_p95_latency_ms: float = float(
        os.getenv("GENERATION_P95_LATENCY_MS", "500")
    )

    # Auth API Parameters
    auth_success_rate_threshold: float = float(
        os.getenv("AUTH_SUCCESS_RATE_THRESHOLD", "0.99")
    )
    auth_p95_latency_ms: float = float(
        os.getenv("AUTH_P95_LATENCY_MS", "200")
    )

    # Payments API Parameters
    payments_success_rate_threshold: float = float(
        os.getenv("PAYMENTS_SUCCESS_RATE_THRESHOLD", "0.95")
    )
    payments_p95_latency_ms: float = float(
        os.getenv("PAYMENTS_P95_LATENCY_MS", "300")
    )

    # Database for synthetic data (isolated)
    database_url: str = os.getenv(
        "LOAD_TEST_DATABASE_URL",
        "postgresql://devstack:devstack@localhost:5432/load_test_db",
    )

    # Redis for testing
    redis_url: str = os.getenv(
        "LOAD_TEST_REDIS_URL", "redis://localhost:6379/10"
    )

    # Report Configuration
    report_dir: str = os.getenv("LOAD_TEST_REPORT_DIR", "./load_test_reports")
    report_format: str = os.getenv("LOAD_TEST_REPORT_FORMAT", "html")

    # Logging
    log_level: str = os.getenv("LOAD_TEST_LOG_LEVEL", "INFO")

    def to_dict(self) -> dict[str, str | int | float]:
        """Convert config to dictionary.

        Returns:
            Configuration as dictionary
        """
        return {
            "host": self.host,
            "timeout": self.timeout,
            "users_min": self.users_min,
            "users_max": self.users_max,
            "spawn_rate": self.spawn_rate,
            "duration_seconds": self.duration_seconds,
            "generation_requests_per_second": self.generation_requests_per_second,
            "generation_success_rate_threshold": self.generation_success_rate_threshold,
            "generation_p95_latency_ms": self.generation_p95_latency_ms,
            "auth_success_rate_threshold": self.auth_success_rate_threshold,
            "auth_p95_latency_ms": self.auth_p95_latency_ms,
            "payments_success_rate_threshold": self.payments_success_rate_threshold,
            "payments_p95_latency_ms": self.payments_p95_latency_ms,
            "database_url": self.database_url,
            "redis_url": self.redis_url,
            "report_dir": self.report_dir,
            "report_format": self.report_format,
            "log_level": self.log_level,
        }


def get_config() -> LoadTestConfig:
    """Get load testing configuration.

    Returns:
        LoadTestConfig instance
    """
    return LoadTestConfig()
