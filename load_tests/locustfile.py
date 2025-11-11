"""Locust load testing suite for auth, generation, and payments APIs.

This module defines load test scenarios targeting:
- Authentication API (login, register, refresh tokens)
- Generation API (create tasks, list tasks, get status)
- Payments API (create payments, list payments)

Run with: locust -f load_tests/locustfile.py
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import structlog
from dotenv import load_dotenv
from locust import HttpUser, between, task

from load_tests.utils import (
    AuthTokenGenerator,
    MetricsCollector,
    TestDataGenerator,
)

load_dotenv(".env.load-testing")

logger = structlog.get_logger(__name__)

# Configuration
API_HOST = os.getenv("LOAD_TEST_HOST", "http://localhost:8000")
AUTH_SUCCESS_THRESHOLD = float(os.getenv("AUTH_SUCCESS_RATE_THRESHOLD", "0.99"))
GENERATION_SUCCESS_THRESHOLD = float(
    os.getenv("GENERATION_SUCCESS_RATE_THRESHOLD", "0.95")
)
PAYMENTS_SUCCESS_THRESHOLD = float(
    os.getenv("PAYMENTS_SUCCESS_RATE_THRESHOLD", "0.95")
)

# Metrics collectors for each API
auth_metrics = MetricsCollector()
generation_metrics = MetricsCollector()
payments_metrics = MetricsCollector()

# Test data generator
data_gen = TestDataGenerator()
token_gen = AuthTokenGenerator()

# Track created resources
created_users: dict[str, Any] = {}
created_generation_tasks: list[str] = []
created_payments: list[str] = []


class AuthUser(HttpUser):
    """Load test user for authentication API."""

    wait_time = between(1, 3)
    host = API_HOST

    @task(3)
    def register_user(self) -> None:
        """Test user registration endpoint."""
        email = data_gen.generate_email()
        password = data_gen.generate_password()

        payload = {
            "email": email,
            "password": password,
        }

        start_time = time.time()
        try:
            response = self.client.post(
                "/api/v1/auth/register",
                json=payload,
                timeout=30,
                catch_response=True,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 201 or response.status_code == 200:
                response.success()
                created_users[email] = {"password": password}
                auth_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
                logger.info(
                    "register_user_success",
                    email=email,
                    response_time_ms=response_time_ms,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                auth_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
                logger.warning(
                    "register_user_failed",
                    email=email,
                    status_code=response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            auth_metrics.record_error(str(e))
            logger.error("register_user_error", error=str(e))

    @task(5)
    def login_user(self) -> None:
        """Test user login endpoint."""
        if not created_users:
            return

        email = list(created_users.keys())[0]
        password = created_users[email]["password"]

        payload = {"email": email, "password": password}

        start_time = time.time()
        try:
            response = self.client.post(
                "/api/v1/auth/login",
                json=payload,
                timeout=30,
                catch_response=True,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                response.success()
                auth_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
                logger.info(
                    "login_user_success",
                    email=email,
                    response_time_ms=response_time_ms,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                auth_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            auth_metrics.record_error(str(e))
            logger.error("login_user_error", error=str(e))

    @task(2)
    def check_health(self) -> None:
        """Test health check endpoint."""
        start_time = time.time()
        try:
            response = self.client.get(
                "/health", timeout=30, catch_response=True
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                response.success()
                auth_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                auth_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            auth_metrics.record_error(str(e))


class GenerationUser(HttpUser):
    """Load test user for generation API."""

    wait_time = between(1, 4)
    host = API_HOST

    def on_start(self) -> None:
        """Initialize test user with auth token."""
        self.auth_token = token_gen.generate_jwt_token(
            "test-user-1", "test@example.com"
        )
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

    @task(7)
    def create_generation_task(self) -> None:
        """Test generation task creation."""
        params = data_gen.generate_generation_params()

        payload = {
            "prompt": params["prompt"],
            "model": params["model"],
            "temperature": params["temperature"],
            "max_tokens": params["max_tokens"],
        }

        start_time = time.time()
        try:
            response = self.client.post(
                "/api/v1/generation/create",
                json=payload,
                headers=self.headers,
                timeout=30,
                catch_response=True,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code in [200, 201, 202]:
                try:
                    data = response.json()
                    task_id = data.get("id") or data.get("task_id")
                    if task_id:
                        created_generation_tasks.append(task_id)
                except (json.JSONDecodeError, KeyError):
                    pass

                response.success()
                generation_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
                logger.info(
                    "create_generation_success",
                    response_time_ms=response_time_ms,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                generation_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
                logger.warning(
                    "create_generation_failed",
                    status_code=response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            generation_metrics.record_error(str(e))
            logger.error("create_generation_error", error=str(e))

    @task(3)
    def list_generation_tasks(self) -> None:
        """Test generation task listing."""
        start_time = time.time()
        try:
            response = self.client.get(
                "/api/v1/generation/list",
                headers=self.headers,
                timeout=30,
                catch_response=True,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                response.success()
                generation_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                generation_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            generation_metrics.record_error(str(e))
            logger.error("list_generation_error", error=str(e))

    @task(2)
    def get_generation_status(self) -> None:
        """Test getting generation task status."""
        if not created_generation_tasks:
            return

        task_id = created_generation_tasks[0]

        start_time = time.time()
        try:
            response = self.client.get(
                f"/api/v1/generation/{task_id}",
                headers=self.headers,
                timeout=30,
                catch_response=True,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                response.success()
                generation_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                generation_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            generation_metrics.record_error(str(e))
            logger.error("get_generation_status_error", error=str(e))


class PaymentUser(HttpUser):
    """Load test user for payments API."""

    wait_time = between(2, 5)
    host = API_HOST

    def on_start(self) -> None:
        """Initialize test user with auth token."""
        self.auth_token = token_gen.generate_jwt_token(
            "test-user-2", "test2@example.com"
        )
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

    @task(6)
    def create_payment(self) -> None:
        """Test payment creation."""
        params = data_gen.generate_payment_params()

        payload = {
            "plan_id": params["plan_id"],
            "amount": params["amount"],
            "currency": params["currency"],
        }

        start_time = time.time()
        try:
            response = self.client.post(
                "/api/v1/payments/create",
                json=payload,
                headers=self.headers,
                timeout=30,
                catch_response=True,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code in [200, 201]:
                try:
                    data = response.json()
                    payment_id = data.get("id") or data.get("payment_id")
                    if payment_id:
                        created_payments.append(payment_id)
                except (json.JSONDecodeError, KeyError):
                    pass

                response.success()
                payments_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
                logger.info(
                    "create_payment_success",
                    response_time_ms=response_time_ms,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                payments_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
                logger.warning(
                    "create_payment_failed",
                    status_code=response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            payments_metrics.record_error(str(e))
            logger.error("create_payment_error", error=str(e))

    @task(4)
    def list_payments(self) -> None:
        """Test payments listing."""
        start_time = time.time()
        try:
            response = self.client.get(
                "/api/v1/payments",
                headers=self.headers,
                timeout=30,
                catch_response=True,
            )
            response_time_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                response.success()
                payments_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
            else:
                response.failure(f"Unexpected status: {response.status_code}")
                payments_metrics.record_response(
                    response_time_ms,
                    response.status_code,
                )
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            payments_metrics.record_error(str(e))
            logger.error("list_payments_error", error=str(e))
