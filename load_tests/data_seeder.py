"""Synthetic data seeding for load testing.

This module provides utilities to create synthetic test data for load testing
the auth, generation, and payments APIs.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog
from faker import Faker
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

fake = Faker()
logger = structlog.get_logger(__name__)


class DataSeeder:
    """Seeds synthetic data for load testing."""

    def __init__(self, database_url: str, test_user_count: int = 100):
        """Initialize the data seeder.

        Args:
            database_url: SQLAlchemy async database URL
            test_user_count: Number of test users to create
        """
        self.database_url = database_url
        self.test_user_count = test_user_count
        self.engine = None
        self.session_maker = None

    async def connect(self) -> None:
        """Establish database connection."""
        self.engine = create_async_engine(self.database_url, echo=False)
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)

    async def disconnect(self) -> None:
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()

    async def create_test_users(self) -> list[dict[str, Any]]:
        """Create synthetic test users.

        Returns:
            List of created user data
        """
        if not self.session_maker:
            raise RuntimeError("Not connected to database")

        users = []
        async with self.session_maker() as session:
            for i in range(self.test_user_count):
                user_data = {
                    "email": f"loadtest_user_{i}_{fake.uuid4()}@example.com",
                    "username": f"loadtest_{i}_{fake.word()}",
                    "first_name": fake.first_name(),
                    "last_name": fake.last_name(),
                }
                users.append(user_data)
                logger.info("created_test_user", user_id=i, email=user_data["email"])

            # Note: Actual user creation depends on your database schema
            # This is a placeholder for the actual implementation
            await session.commit()

        return users

    async def create_test_subscriptions(
        self, user_ids: list[int]
    ) -> list[dict[str, Any]]:
        """Create synthetic test subscriptions for users.

        Args:
            user_ids: List of user IDs to create subscriptions for

        Returns:
            List of created subscription data
        """
        if not self.session_maker:
            raise RuntimeError("Not connected to database")

        subscriptions = []
        async with self.session_maker() as session:
            for user_id in user_ids:
                subscription_data = {
                    "user_id": user_id,
                    "plan_name": fake.random_element(
                        ["starter", "pro", "enterprise"]
                    ),
                    "is_active": True,
                    "generation_limit": fake.random_int(min=100, max=10000),
                }
                subscriptions.append(subscription_data)

            await session.commit()

        return subscriptions

    async def seed_all(self) -> dict[str, Any]:
        """Seed all synthetic data.

        Returns:
            Dictionary containing created data and statistics
        """
        try:
            await self.connect()
            logger.info("starting_data_seeding", test_users=self.test_user_count)

            users = await self.create_test_users()
            logger.info("users_created", count=len(users))

            result = {
                "users_created": len(users),
                "status": "success",
            }

            logger.info("data_seeding_complete", result=result)
            return result

        except Exception as e:
            logger.error("data_seeding_failed", error=str(e))
            raise
        finally:
            await self.disconnect()


async def seed_test_data(
    database_url: str, test_user_count: int = 100
) -> dict[str, Any]:
    """Convenience function to seed test data.

    Args:
        database_url: SQLAlchemy async database URL
        test_user_count: Number of test users to create

    Returns:
        Dictionary containing created data and statistics
    """
    seeder = DataSeeder(database_url, test_user_count)
    return await seeder.seed_all()


if __name__ == "__main__":
    # Example usage
    db_url = os.getenv(
        "LOAD_TEST_DATABASE_URL", "postgresql://devstack:devstack@localhost:5432/load_test_db"
    )
    asyncio.run(seed_test_data(db_url, test_user_count=100))
