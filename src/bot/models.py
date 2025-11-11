"""Data models used by the Telegram bot."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """User profile information returned by the backend."""

    id: int
    username: str | None = None
    email: str | None = None
    subscription: str | None = None
    credits: int = Field(default=0, ge=0)

    def to_message(self) -> str:
        lines = ["👤 <b>Your profile</b>"]
        if self.username:
            lines.append(f"Username: @{self.username}")
        if self.email:
            lines.append(f"Email: {self.email}")
        if self.subscription:
            lines.append(f"Subscription: {self.subscription}")
        lines.append(f"Credits: {self.credits}")
        return "\n".join(lines)


class SubscriptionStatus(BaseModel):
    """Represents subscription state after /subscribe command."""

    status: Literal["active", "inactive", "pending", "canceled"]
    plan: str | None = None
    renews_at: datetime | None = None

    def to_message(self) -> str:
        lines = ["💳 <b>Subscription status</b>"]
        lines.append(f"Status: {self.status.title()}")
        if self.plan:
            lines.append(f"Plan: {self.plan}")
        if self.renews_at:
            formatted = self.renews_at.strftime("%Y-%m-%d %H:%M UTC")
            lines.append(f"Renews at: {formatted}")
        return "\n".join(lines)


class Balance(BaseModel):
    """Represents account balance/credits."""

    credits: int = Field(ge=0)
    currency: str = "credits"

    def to_message(self) -> str:
        return f"💰 Balance: {self.credits} {self.currency}".strip()


class GenerationHistoryItem(BaseModel):
    """A single generation entry."""

    id: str
    created_at: datetime
    status: str
    prompt: str
    result_url: str | None = None
    category: str | None = None

    def to_message(self) -> str:
        lines = [f"• {self.prompt} ({self.status})"]
        lines.append(self.created_at.strftime("%Y-%m-%d %H:%M"))
        if self.category:
            lines.append(f"Category: {self.category}")
        if self.result_url:
            lines.append(f"Result: {self.result_url}")
        return " — ".join(lines)


class GenerationRequest(BaseModel):
    """Parameters forwarded to the backend generation API."""

    category: str
    prompt: str
    parameters: dict[str, Any]
    source_file_id: str
    source_file_name: str | None = None


class GenerationJob(BaseModel):
    """Represents the job created by the backend."""

    job_id: str


class GenerationResult(BaseModel):
    """Final generation payload delivered over WebSocket."""

    job_id: str
    image_url: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_message(self) -> str:
        lines: list[str] = ["✅ <b>Generation complete!</b>"]
        if self.description:
            lines.append(self.description)
        if self.image_url:
            lines.append(f"Result: {self.image_url}")
        if self.metadata:
            formatted_meta = ", ".join(
                f"{key}={value}" for key, value in sorted(self.metadata.items())
            )
            lines.append(f"Metadata: {formatted_meta}")
        return "\n".join(lines)


class GenerationUpdate(BaseModel):
    """Streaming update coming from the backend over WebSockets."""

    status: Literal["queued", "progress", "completed", "failed"]
    progress: int | None = Field(default=None, ge=0, le=100)
    message: str | None = None
    eta_seconds: int | None = Field(default=None, ge=0)
    result: GenerationResult | None = None

    def is_terminal(self) -> bool:
        return self.status in {"completed", "failed"}

    def format_progress(self) -> str:
        icon = {"queued": "⏳", "progress": "🚀", "completed": "✅", "failed": "❌"}[
            self.status
        ]
        parts: list[str] = [icon]
        if self.status == "progress" and self.progress is not None:
            parts.append(f"Progress: {self.progress}%")
        elif self.status == "queued":
            parts.append("Queued")
        elif self.status == "completed":
            parts.append("Completed")
        elif self.status == "failed":
            parts.append("Failed")
        if self.message:
            parts.append(self.message)
        return " — ".join(parts)


def format_history(items: Iterable[GenerationHistoryItem]) -> str:
    lines = ["🗂️ <b>Your recent generations</b>"]
    found = False
    for item in items:
        found = True
        lines.append(item.to_message())
    if not found:
        lines.append(
            "No generation history yet. Use /generate to create something new!"
        )
    return "\n".join(lines)
