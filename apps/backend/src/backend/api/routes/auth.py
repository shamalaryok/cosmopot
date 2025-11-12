from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, TypedDict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.analytics.decorators import AnalyticsTracker
from backend.analytics.dependencies import get_analytics_service
from backend.analytics.service import AnalyticsService
from backend.auth.dependencies import (
    CurrentUser,
    get_auth_service,
    get_current_user,
    get_rate_limiter,
    get_token_service,
)
from backend.auth.exceptions import (
    AccountDisabledError,
    AccountNotVerifiedError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    SessionRevokedError,
    TokenExpiredError,
    VerificationTokenInvalidError,
)
from backend.auth.models import User
from backend.auth.rate_limiter import RateLimiter
from backend.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserRead,
    VerifyAccountRequest,
)
from backend.auth.service import AuthResult, AuthService
from backend.auth.tokens import TokenService
from backend.core.config import Settings, get_settings
from backend.db.dependencies import get_db_session
from backend.services.telegram import (
    TelegramAuthError,
    TelegramAuthInactiveUserError,
    TelegramAuthReplayError,
    TelegramAuthService,
    TelegramAuthSignatureError,
    TelegramLoginPayload,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class _CookieKwargs(TypedDict, total=False):
    httponly: bool
    secure: bool
    samesite: Literal["lax", "strict", "none"]
    path: str
    domain: str


def _now() -> datetime:
    return datetime.now(UTC)


def _user_to_read(user: User) -> UserRead:
    return UserRead.model_validate(user)


def _cookie_kwargs(settings: Settings) -> _CookieKwargs:
    kwargs: _CookieKwargs = {
        "httponly": True,
        "secure": settings.jwt.cookie_secure,
        "samesite": settings.jwt.cookie_samesite,
        "path": settings.jwt.cookie_path,
    }
    if settings.jwt.cookie_domain is not None:
        kwargs["domain"] = settings.jwt.cookie_domain
    return kwargs


def _set_auth_cookies(
    response: Response,
    settings: Settings,
    tokens: AuthResult,
) -> None:
    access_token = tokens.tokens.access_token
    refresh_token = tokens.tokens.refresh_token

    cookie_kwargs = _cookie_kwargs(settings)

    access_expires = settings.jwt.access_token_exp_minutes * 60
    refresh_expires = settings.jwt.refresh_token_exp_days * 24 * 60 * 60

    response.set_cookie(
        settings.jwt.access_cookie_name,
        access_token,
        max_age=access_expires,
        **cookie_kwargs,
    )
    response.set_cookie(
        settings.jwt.refresh_cookie_name,
        refresh_token,
        max_age=refresh_expires,
        **cookie_kwargs,
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    cookie_kwargs = _cookie_kwargs(settings)

    response.set_cookie(settings.jwt.access_cookie_name, "", max_age=0, **cookie_kwargs)
    response.set_cookie(
        settings.jwt.refresh_cookie_name, "", max_age=0, **cookie_kwargs
    )


def _auth_result_to_response(result: AuthResult) -> TokenResponse:
    access_expires_in = max(
        0,
        int((result.tokens.access_expires_at - _now()).total_seconds()),
    )
    refresh_expires_in = max(
        0,
        int((result.tokens.refresh_expires_at - _now()).total_seconds()),
    )
    return TokenResponse(
        access_token=result.tokens.access_token,
        refresh_token=result.tokens.refresh_token,
        expires_in=access_expires_in,
        refresh_expires_in=refresh_expires_in,
        session_id=result.tokens.session_id,
        user=_user_to_read(result.user),
    )


def _map_auth_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EmailAlreadyRegisteredError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    if isinstance(exc, InvalidCredentialsError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    if isinstance(exc, AccountNotVerifiedError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account verification required",
        )
    if isinstance(exc, AccountDisabledError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled"
        )
    if isinstance(exc, VerificationTokenInvalidError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token"
        )
    if isinstance(exc, TokenExpiredError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
        )
    if isinstance(exc, SessionRevokedError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer valid",
        )
    if isinstance(exc, InvalidTokenError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Authentication error"
    )


@router.post(
    "/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register_user(
    payload: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    session: AsyncSession = Depends(get_db_session),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> RegisterResponse:
    await rate_limiter.check("auth:register", payload.email.lower())
    logger = structlog.get_logger("backend.auth")
    email_domain = payload.email.split("@")[1] if "@" in payload.email else None

    # Track signup start
    analytics_tracker = AnalyticsTracker(analytics_service, session)
    await analytics_tracker.track_signup(
        user_id="",  # Will be updated after user creation
        signup_method="email",
        user_properties={"signup_source": "web"},
    )

    try:
        user, token = await auth_service.register(
            session,
            email=payload.email,
            password=payload.password,
        )

        # Track successful signup
        await analytics_tracker.track_signup(
            user_id=str(user.id),
            signup_method="email",
            user_properties={
                "signup_source": "web",
                "email_domain": email_domain,
            },
        )

    except Exception as exc:
        logger.exception("register_failed", email=payload.email)
        # Track signup failure
        await analytics_tracker.track_signup(
            user_id="",
            signup_method="email",
            user_properties={
                "signup_source": "web",
                "email_domain": email_domain,
                "error": str(exc),
            },
        )
        raise _map_auth_error(exc) from exc

    return RegisterResponse(user=_user_to_read(user), verification_token=token)


@router.post("/verify", response_model=MessageResponse)
async def verify_account(
    payload: VerifyAccountRequest,
    auth_service: AuthService = Depends(get_auth_service),
    session: AsyncSession = Depends(get_db_session),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> MessageResponse:
    await rate_limiter.check("auth:verify", payload.token[-12:])
    logger = structlog.get_logger("backend.auth")
    try:
        await auth_service.verify_account(session, token=payload.token)
    except Exception as exc:
        logger.exception("verify_failed", token_suffix=payload.token[-12:])
        raise _map_auth_error(exc) from exc

    return MessageResponse(message="Account verified")


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    analytics_service: AnalyticsService = Depends(get_analytics_service),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> TokenResponse:
    await rate_limiter.check("auth:login", payload.email.lower())
    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    # Track login attempt
    analytics_tracker = AnalyticsTracker(analytics_service, session)

    try:
        result = await auth_service.login(
            session,
            email=payload.email,
            password=payload.password,
            user_agent=user_agent,
            ip_address=ip_address,
        )

        # Track successful login
        await analytics_tracker.track_login(
            user_id=str(result.user.id),
            login_method="email",
            user_agent=user_agent,
            ip_address=ip_address,
        )

    except Exception as exc:
        # Track failed login
        await analytics_tracker.track_login(
            user_id="",
            login_method="email",
            user_agent=user_agent,
            ip_address=ip_address,
            error=str(exc),
        )
        raise _map_auth_error(exc) from exc

    _set_auth_cookies(response, settings, result)
    return _auth_result_to_response(result)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    token_service: TokenService = Depends(get_token_service),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> TokenResponse:
    raw_token = payload.refresh_token or request.cookies.get(
        settings.jwt.refresh_cookie_name
    )
    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Refresh token missing"
        )

    try:
        decoded = token_service.decode_refresh_token(raw_token)
    except Exception as exc:
        raise _map_auth_error(exc) from exc

    await rate_limiter.check("auth:refresh", str(decoded.subject))

    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    try:
        result = await auth_service.refresh(
            session,
            refresh_token=raw_token,
            user_agent=user_agent,
            ip_address=ip_address,
        )
    except Exception as exc:
        raise _map_auth_error(exc) from exc

    _set_auth_cookies(response, settings, result)
    return _auth_result_to_response(result)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    token_service: TokenService = Depends(get_token_service),
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> MessageResponse:
    raw_token = payload.refresh_token or request.cookies.get(
        settings.jwt.refresh_cookie_name
    )
    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token required for logout",
        )

    decoded = None
    try:
        decoded = token_service.decode_refresh_token(raw_token)
    except (TokenExpiredError, InvalidTokenError):
        decoded = None
    except Exception as exc:
        raise _map_auth_error(exc) from exc

    if decoded is not None:
        await rate_limiter.check("auth:logout", str(decoded.subject))
        try:
            await auth_service.logout(session, refresh_token=raw_token)
        except (SessionRevokedError, InvalidTokenError, TokenExpiredError):
            pass
        except Exception as exc:
            raise _map_auth_error(exc) from exc

    _clear_auth_cookies(response, settings)
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserRead)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserRead:
    user = await session.get(User, current_user.id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return _user_to_read(user)


class TelegramAuthResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime

    model_config = ConfigDict(json_encoders={datetime: lambda value: value.isoformat()})


@router.post("/telegram", response_model=TelegramAuthResponse)
async def telegram_authenticate(
    request: Request,
    payload: TelegramLoginPayload,
    session: AsyncSession = Depends(get_db_session),
) -> TelegramAuthResponse:
    settings: Settings = request.app.state.settings

    if settings.telegram_bot_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram authentication is not configured",
        )

    service = TelegramAuthService(
        bot_token=settings.telegram_bot_token.get_secret_value(),
        login_ttl_seconds=settings.telegram_login_ttl_seconds,
        jwt_secret=settings.jwt_secret_key.get_secret_value(),
        jwt_algorithm=settings.jwt_algorithm,
        access_token_ttl_seconds=settings.jwt_access_ttl_seconds,
    )

    try:
        result = await service.authenticate(
            session,
            payload,
            user_agent=request.headers.get("user-agent"),
            ip_address=_extract_client_ip(request),
        )
        await session.commit()
    except TelegramAuthSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except TelegramAuthReplayError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    except TelegramAuthInactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except TelegramAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return TelegramAuthResponse(
        access_token=result.access_token,
        token_type=result.token_type,
        expires_at=result.expires_at,
    )


def _extract_client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client is not None:
        return request.client.host

    return None
