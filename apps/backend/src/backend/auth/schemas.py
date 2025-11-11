from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.auth.enums import UserRole


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    is_verified: bool

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class RegisterResponse(BaseModel):
    user: UserRead
    verification_token: str


class VerifyAccountRequest(BaseModel):
    token: str = Field(min_length=16)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    refresh_expires_in: int = Field(
        ..., description="Refresh token lifetime in seconds"
    )
    session_id: uuid.UUID
    user: UserRead


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(
        default=None, description="Optional refresh token override"
    )


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class MessageResponse(BaseModel):
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
