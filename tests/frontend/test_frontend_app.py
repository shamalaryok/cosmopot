from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

try:
    from frontend.app.gateway import AuthTokens
    from frontend.app.main import app, get_gateway

    FRONTEND_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional frontend package
    FRONTEND_AVAILABLE = False
    pytestmark = pytest.mark.skip(reason="frontend application not available")
    AuthTokens = None  # type: ignore[misc, assignment]
    app = None  # type: ignore[assignment]
    get_gateway = None  # type: ignore[assignment]


@dataclass
class DummyGateway:
    health_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "status": "ok",
            "dependencies": {
                "postgres": {"status": "ok"},
                "redis": {"status": "ok"},
            },
        }
    )
    user_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "id": 42,
            "email": "demo@example.com",
            "balance": "25.00",
            "quotas": {
                "plan": "Creator",
                "monthly_allocation": 2000,
                "remaining_allocation": 1800,
                "requires_top_up": False,
            },
            "subscription_tier": "creator",
            "profile": {
                "first_name": "Demo",
                "last_name": "User",
                "country": "Wonderland",
                "city": "Fable",
                "phone_number": "+1234567",
                "telegram_id": "@demo",
            },
        }
    )

    tasks_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "items": [
                {
                    "id": "task-1",
                    "status": "queued",
                    "prompt": "Render skyline",
                    "parameters": {
                        "width": 512,
                        "height": 512,
                        "model": "stable-diffusion-xl",
                    },
                    "subscription_tier": "creator",
                    "created_at": "2023-10-31T10:00:00Z",
                    "input_url": "https://example.com/seed.png",
                }
            ],
            "pagination": {"page": 1, "page_size": 10, "has_next": False},
        }
    )
    payment_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "confirmation_url": "https://payments.example/checkout"
        }
    )
    task_messages: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"type": "snapshot", "status": "queued"},
            {"type": "update", "status": "completed", "terminal": True},
        ]
    )

    login_calls: list[tuple[str, str]] = field(default_factory=list)
    update_payloads: list[dict[str, Any]] = field(default_factory=list)
    generation_payloads: list[dict[str, Any]] = field(default_factory=list)
    logout_called: bool = False

    async def health(self) -> dict[str, Any]:
        return self.health_payload

    async def login(self, email: str, password: str) -> AuthTokens:
        self.login_calls.append((email, password))
        return AuthTokens(
            access_token="access-token",
            refresh_token="refresh-token",
            user={"id": "auth-user", "email": email},
        )

    async def refresh(self, refresh_token: str) -> AuthTokens:
        return AuthTokens(access_token="new-access", refresh_token=refresh_token)

    async def logout(self, refresh_token: str | None) -> None:
        self.logout_called = True

    async def get_current_user(
        self, *, access_token: str, refresh_token: str | None
    ) -> tuple[dict[str, Any], AuthTokens | None]:
        return self.user_payload, None

    async def update_profile(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], AuthTokens | None]:
        self.update_payloads.append(payload)
        return payload, None

    async def create_generation(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        prompt: str,
        parameters: dict[str, Any],
        upload: tuple[str, bytes, str],
    ) -> tuple[dict[str, Any], AuthTokens | None]:
        self.generation_payloads.append(
            {"prompt": prompt, "parameters": parameters, "filename": upload[0]}
        )
        return {"task_id": "task-queued", "status": "queued"}, None

    async def list_tasks(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        page: int,
        page_size: int,
    ) -> tuple[dict[str, Any], AuthTokens | None]:
        return self.tasks_payload, None

    async def create_payment(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], AuthTokens | None]:
        return self.payment_payload, None

    async def stream_task_updates(
        self,
        *,
        user_id: int,
        task_id: str,
        access_token: str,
    ) -> AsyncGenerator[str, None]:
        for message in self.task_messages:
            yield json.dumps(message)


@pytest.fixture
def stub_gateway() -> DummyGateway:
    return DummyGateway()


@pytest.fixture
def client(stub_gateway: DummyGateway) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_gateway] = lambda: stub_gateway
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def login(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"email": "demo@example.com", "password": "Password123!"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_homepage_renders_health(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Platform status" in response.text


def test_login_flow_sets_session(client: TestClient) -> None:
    login(client)
    response = client.get("/generate")
    assert response.status_code == 200
    assert "Submit a generation task" in response.text


def test_profile_requires_auth_redirects(client: TestClient) -> None:
    response = client.get("/profile", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")


def test_profile_update_success(client: TestClient, stub_gateway: DummyGateway) -> None:
    login(client)
    response = client.post(
        "/profile",
        data={"first_name": "New", "city": "Metropolis"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert stub_gateway.update_payloads[-1] == {
        "first_name": "New",
        "city": "Metropolis",
    }


def test_generate_invalid_upload_error(client: TestClient) -> None:
    login(client)
    response = client.post(
        "/generate",
        data={"prompt": "City skyline"},
        files={"image": ("seed.txt", b"text", "text/plain")},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "PNG or JPEG" in response.text


def test_generate_success_redirects_history(
    client: TestClient, stub_gateway: DummyGateway
) -> None:
    login(client)
    response = client.post(
        "/generate",
        data={
            "prompt": "Futuristic city",
            "width": "640",
            "height": "640",
            "inference_steps": "40",
            "guidance_scale": "8",
            "model": "stable-diffusion-xl",
            "scheduler": "ddim",
        },
        files={"image": ("seed.png", b"fake-bytes", "image/png")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/history")
    payload = stub_gateway.generation_payloads[-1]
    assert payload["prompt"] == "Futuristic city"


def test_history_page_renders_tasks(client: TestClient) -> None:
    login(client)
    response = client.get("/history")
    assert response.status_code == 200
    assert "Render skyline" in response.text


def test_pricing_checkout_redirects(client: TestClient) -> None:
    login(client)
    response = client.post(
        "/pricing/checkout",
        data={"plan_code": "basic"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("https://payments.example/checkout")


def test_logout_clears_session(client: TestClient, stub_gateway: DummyGateway) -> None:
    login(client)
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert stub_gateway.logout_called is True
    response = client.get("/generate", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/login")


def test_websocket_proxy_streams_updates(client: TestClient) -> None:
    login(client)
    with client.websocket_connect("/ws/tasks/task-1") as websocket:
        message = websocket.receive_text()
        assert "queued" in message
        message = websocket.receive_text()
        assert "completed" in message
