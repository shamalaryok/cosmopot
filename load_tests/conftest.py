"""Pytest configuration for load testing."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load environment from .env.load-testing
ENV_FILE = Path(__file__).parent.parent / ".env.load-testing"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)


@pytest.fixture
def load_test_config() -> dict[str, str | int | float]:
    """Provide load testing configuration.

    Returns:
        Dictionary with configuration
    """
    from load_tests.config import get_config

    config = get_config()
    return config.to_dict()


@pytest.fixture
def test_data_generator():
    """Provide test data generator.

    Returns:
        TestDataGenerator instance
    """
    from load_tests.utils import TestDataGenerator

    return TestDataGenerator()


@pytest.fixture
def token_generator():
    """Provide token generator.

    Returns:
        AuthTokenGenerator instance
    """
    from load_tests.utils import AuthTokenGenerator

    return AuthTokenGenerator()


@pytest.fixture
def metrics_collector():
    """Provide metrics collector.

    Returns:
        MetricsCollector instance
    """
    from load_tests.utils import MetricsCollector

    return MetricsCollector()


@pytest.fixture
async def data_seeder():
    """Provide data seeder.

    Yields:
        DataSeeder instance
    """
    from load_tests.data_seeder import DataSeeder

    db_url = os.getenv(
        "LOAD_TEST_DATABASE_URL",
        "postgresql://devstack:devstack@localhost:5432/load_test_db",
    )

    seeder = DataSeeder(db_url, test_user_count=50)

    try:
        yield seeder
    finally:
        pass  # Cleanup handled by DataSeeder.disconnect()
