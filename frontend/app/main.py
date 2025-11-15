from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeAlias, TypedDict, cast

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.middleware.sessions import SessionMiddleware

from .gateway import (
    AuthTokens,
    BackendError,
    BackendGateway,
    GenerationTaskPayload,
    PaymentPayload,
    TaskListPayload,
    UnauthorizedError,
    UserPayload,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


class FlashMessage(TypedDict):
    level: str
    text: str


JSONDict: TypeAlias = dict[str, Any]


_PROMPT_CATALOG = [
    {
        "title": "Neon skyline",
        "prompt": (
            "a futuristic neon-lit skyline at dusk, ultra wide angle, "
            "cinematic lighting, volumetric fog"
        ),
        "category": "Futurism",
    },
    {
        "title": "Forest spirits",
        "prompt": (
            "ethereal spirits drifting through an ancient forest, "
            "bioluminescent highlights, studio ghibli style"
        ),
        "category": "Fantasy",
    },
    {
        "title": "Architectural concept",
        "prompt": (
            "minimalist concrete museum atrium flooded with natural light, "
            "brutalist symmetry, ray-traced reflections"
        ),
        "category": "Concept art",
    },
    {
        "title": "Product hero",
        "prompt": (
            "sleek wearable device floating above a rippled water surface, "
            "dramatic rim lighting, product photography"
        ),
        "category": "Product",
    },
    {
        "title": "Editorial portrait",
        "prompt": (
            "editorial portrait of a musician surrounded by floating "
            "musical notes, soft depth of field, warm tones"
        ),
        "category": "Portrait",
    },
    {
        "title": "Nature macro",
        "prompt": (
            "super macro shot of a dew-covered leaf with prismatic refraction, "
            "8k, hyperrealistic"
        ),
        "category": "Nature",
    },
]


_PRICING_PLANS = [
    {
        "code": "basic",
        "name": "Creator",
        "description": "Essential toolkit with fast queue access for solo makers.",
        "price": "9.99",
        "currency": "RUB",
        "features": [
            "2k monthly render credits",
            "HD upscaling",
            "Prompt catalog access",
            "Email support",
        ],
        "badge": "Popular",
    },
    {
        "code": "pro",
        "name": "Studio",
        "description": (
            "Priority rendering, collaboration seats, and automation hooks."
        ),
        "price": "29.99",
        "currency": "RUB",
        "features": [
            "10k monthly render credits",
            "Priority queueing",
            "Webhook callbacks",
            "Slack support",
        ],
        "badge": "New",
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": (
            "Guaranteed throughput with advanced compliance and premium care."
        ),
        "price": "99.99",
        "currency": "RUB",
        "features": [
            "Unlimited team credits",
            "Dedicated rendering pods",
            "Single sign-on",
            "24/7 incident hotline",
        ],
        "badge": None,
    },
]

JSONPrimitive = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


class AuthSession(TypedDict, total=False):
    access_token: str
    refresh_token: str | None
    session_id: str | None
    account: JSONValue | None
    user: JSONValue | None
    user_id: int | None
    email: str | None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    backend_url: str = "http://backend:8000"
    backend_ws_url: str | None = None
    session_secret: str = "front-secret-key"
    max_upload_bytes: int = 8 * 1024 * 1024
    prompt_catalog: list[dict[str, str]] = Field(
        default_factory=lambda: list(_PROMPT_CATALOG)
    )


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
settings = Settings()
app = FastAPI(title="DreamFoundry")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
)

_gateway = BackendGateway(
    base_url=settings.backend_url, websocket_base_url=settings.backend_ws_url
)
app.state.gateway = _gateway
app.state.settings = settings


def get_gateway() -> BackendGateway:
    gateway = getattr(app.state, "gateway", None)
    if isinstance(gateway, BackendGateway):
        return gateway
    raise RuntimeError("Backend gateway is not configured")


def _json_default(value: Any) -> str:
    return str(value)


def _serialise(value: Any) -> JSONValue:
    return cast(JSONValue, json.loads(json.dumps(value, default=_json_default)))


def _is_json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


def _consume_flash(request: Request) -> list[FlashMessage]:
    messages_raw = request.session.pop("_messages", [])
    if not isinstance(messages_raw, list):
        return []
    messages: list[FlashMessage] = []
    for item in messages_raw:
        if isinstance(item, Mapping):
            level = item.get("level")
            text = item.get("text")
            if isinstance(level, str) and isinstance(text, str):
                messages.append({"level": level, "text": text})
    return messages


def _make_flash(level: str, text: str) -> FlashMessage:
    return {"level": level, "text": text}


def _flash(request: Request, level: str, message: str) -> None:
    messages_raw = request.session.get("_messages")
    if not isinstance(messages_raw, list):
        messages_raw = []
    flash_message = _make_flash(level, message)
    messages_raw.append(flash_message)
    request.session["_messages"] = messages_raw


def _normalise_auth_session(raw: Any) -> AuthSession | None:
    if not isinstance(raw, Mapping):
        return None
    access_token = raw.get("access_token")
    if not isinstance(access_token, str):
        return None

    session: AuthSession = {"access_token": access_token}
    refresh_token = raw.get("refresh_token")
    if isinstance(refresh_token, str) or refresh_token is None:
        session["refresh_token"] = refresh_token

    session_id = raw.get("session_id")
    if isinstance(session_id, str) or session_id is None:
        session["session_id"] = session_id

    account = raw.get("account")
    if _is_json_value(account):
        session["account"] = cast(JSONValue | None, account)

    user_value = raw.get("user")
    if _is_json_value(user_value):
        session["user"] = cast(JSONValue | None, user_value)

    user_id = raw.get("user_id")
    if isinstance(user_id, int):
        session["user_id"] = user_id

    email = raw.get("email")
    if isinstance(email, str):
        session["email"] = email

    return session


def _session_user_payload(auth: AuthSession | None) -> UserPayload:
    if not auth:
        return cast(UserPayload, {})
    user_value = auth.get("user")
    if isinstance(user_value, dict):
        return cast(UserPayload, user_value)
    return cast(UserPayload, {})


def _get_auth_session(request: Request) -> AuthSession | None:
    auth = _normalise_auth_session(request.session.get("auth"))
    if auth is not None:
        request.session["auth"] = auth
    return auth


def _store_auth_session(
    request: Request, tokens: AuthTokens, user_payload: UserPayload
) -> None:
    session: AuthSession = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "session_id": tokens.session_id,
        "account": _serialise(tokens.user) if tokens.user else None,
        "user": _serialise(user_payload),
    }
    user_id = user_payload.get("id")
    if isinstance(user_id, int):
        session["user_id"] = user_id
    email = user_payload.get("email")
    if isinstance(email, str):
        session["email"] = email
    request.session["auth"] = session


def _merge_auth_session(
    request: Request,
    *,
    tokens: AuthTokens | None = None,
    user_payload: UserPayload | None = None,
) -> None:
    session = _get_auth_session(request)
    if session is None:
        return

    if tokens is not None:
        session["access_token"] = tokens.access_token
        session["refresh_token"] = tokens.refresh_token
        session["session_id"] = tokens.session_id
        if tokens.user is not None:
            session["account"] = _serialise(tokens.user)

    if user_payload is not None:
        session["user"] = _serialise(user_payload)
        user_id = user_payload.get("id")
        if isinstance(user_id, int):
            session["user_id"] = user_id
        elif "user_id" in session:
            session.pop("user_id")
        email = user_payload.get("email")
        if isinstance(email, str):
            session["email"] = email
        elif "email" in session:
            session.pop("email")

    request.session["auth"] = session


def _clear_auth(request: Request) -> None:
    request.session.pop("auth", None)


@app.get("/", response_class=HTMLResponse, name="home")
async def home(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> HTMLResponse:
    messages = _consume_flash(request)
    health: JSONDict | None = None
    error: str | None = None
    try:
        health = await gateway.health()
    except Exception as exc:  # pragma: no cover - defensive
        error = str(exc)
    context: dict[str, object] = {
        "request": request,
        "messages": messages,
        "health": health or {},
        "error": error,
        "prompt_catalog": settings.prompt_catalog[:3],
    }
    return templates.TemplateResponse("home.html", context)


@app.get("/login", response_class=HTMLResponse, name="login_page")
async def login_page(request: Request) -> Response | RedirectResponse:
    if _get_auth_session(request):
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )
    context: dict[str, object] = {
        "request": request,
        "messages": _consume_flash(request),
        "form_error": None,
        "email": "",
    }
    return templates.TemplateResponse("login.html", context)


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    email: str = Form(..., description="Email address"),
    password: str = Form(..., description="Password"),
) -> Response | RedirectResponse:
    messages = _consume_flash(request)
    if _get_auth_session(request):
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )
    try:
        tokens = await gateway.login(email=email, password=password)
        user_payload, refreshed = await gateway.get_current_user(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )
        if refreshed:
            tokens = refreshed
        _store_auth_session(request, tokens, user_payload)
        _flash(request, "success", "Welcome back! Your dashboard is ready.")
        return RedirectResponse(
            url=request.url_for("generate"), status_code=status.HTTP_303_SEE_OTHER
        )
    except BackendError as exc:
        context_messages: list[FlashMessage] = [
            *messages,
            _make_flash("error", exc.message),
        ]
        context: dict[str, object] = {
            "request": request,
            "messages": context_messages,
            "form_error": exc.message,
            "email": email,
        }
        return templates.TemplateResponse(
            "login.html", context, status_code=status.HTTP_400_BAD_REQUEST
        )


@app.post("/logout")
async def logout(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> RedirectResponse:
    auth = _get_auth_session(request)
    refresh_token = auth.get("refresh_token") if auth else None
    if refresh_token:
        try:
            await gateway.logout(refresh_token)
        except BackendError:  # pragma: no cover - best effort
            pass
    _clear_auth(request)
    _flash(request, "success", "You have been signed out.")
    return RedirectResponse(
        url=request.url_for("home"), status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/profile", response_class=HTMLResponse, name="profile")
async def profile(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> Response | RedirectResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to manage your profile.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    cached_user = _session_user_payload(auth)
    try:
        user_payload, tokens = await gateway.get_current_user(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
        )
        _merge_auth_session(request, tokens=tokens, user_payload=user_payload)
    except UnauthorizedError:
        _clear_auth(request)
        _flash(request, "info", "Your session has expired. Please log in again.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )
    except BackendError as exc:
        context_messages: list[FlashMessage] = [
            *messages,
            {"level": "error", "text": exc.message},
        ]
        error_context: dict[str, object] = {
            "request": request,
            "messages": context_messages,
            "user": cached_user,
            "quotas": {},
            "load_error": exc.message,
        }
        return templates.TemplateResponse(
            "profile.html", error_context, status_code=status.HTTP_502_BAD_GATEWAY
        )

    success_context: dict[str, object] = {
        "request": request,
        "messages": messages,
        "user": user_payload,
        "load_error": None,
    }
    return templates.TemplateResponse("profile.html", success_context)


@app.post("/profile", response_class=HTMLResponse)
async def update_profile(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),
    phone_number: str | None = Form(None),
    country: str | None = Form(None),
    city: str | None = Form(None),
    telegram_id: str | None = Form(None),
) -> Response | RedirectResponse:
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Please sign in to update your profile.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    cached_user = _session_user_payload(auth)

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "phone_number": phone_number,
        "country": country,
        "city": city,
        "telegram_id": telegram_id,
    }
    filtered = {key: value for key, value in payload.items() if value}
    if not filtered:
        _flash(request, "warning", "Add at least one field before saving.")
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        _, tokens = await gateway.update_profile(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            payload=filtered,
        )
        _merge_auth_session(request, tokens=tokens)
        user_payload, refreshed = await gateway.get_current_user(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
        )
        _merge_auth_session(request, tokens=refreshed, user_payload=user_payload)
        _flash(request, "success", "Profile updated successfully.")
        return RedirectResponse(
            url=request.url_for("profile"), status_code=status.HTTP_303_SEE_OTHER
        )
    except BackendError as exc:
        messages = _consume_flash(request)
        context_messages: list[FlashMessage] = [
            *messages,
            {"level": "error", "text": exc.message},
        ]
        context: dict[str, object] = {
            "request": request,
            "messages": context_messages,
            "user": cached_user,
            "load_error": exc.message,
        }
        return templates.TemplateResponse(
            "profile.html", context, status_code=status.HTTP_400_BAD_REQUEST
        )


@app.get("/generate", response_class=HTMLResponse, name="generate")
async def generate_page(
    request: Request, gateway: BackendGateway = Depends(get_gateway)
) -> Response | RedirectResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to enqueue new generations.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    user_payload = _session_user_payload(auth)
    try:
        user_payload, tokens = await gateway.get_current_user(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
        )
        _merge_auth_session(request, tokens=tokens, user_payload=user_payload)
    except BackendError as exc:
        user_payload = _session_user_payload(auth)
        error_message = _make_flash("error", exc.message)
        messages.append(error_message)
    context: dict[str, object] = {
        "request": request,
        "messages": messages,
        "user": user_payload,
        "prompt_catalog": settings.prompt_catalog,
        "max_upload": settings.max_upload_bytes,
    }
    return templates.TemplateResponse("generate.html", context)


@app.post("/generate", response_class=HTMLResponse)
async def generate_submit(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    prompt: str = Form(...),
    width: str = Form("512"),
    height: str = Form("512"),
    inference_steps: str = Form("30"),
    guidance_scale: str = Form("7.5"),
    seed: str | None = Form(None),
    model: str = Form("stable-diffusion-xl"),
    scheduler: str = Form("ddim"),
    image: UploadFile = File(...),
) -> Response | RedirectResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to create new generations.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    errors: list[str] = []
    prompt_value = prompt.strip()
    if not prompt_value:
        errors.append("Prompt cannot be empty.")

    try:
        width_value = int(width)
        height_value = int(height)
        if not 64 <= width_value <= 2048 or not 64 <= height_value <= 2048:
            errors.append("Dimensions must be between 64 and 2048 pixels.")
    except ValueError:
        errors.append("Width and height must be whole numbers.")
        width_value = 512
        height_value = 512

    try:
        steps_value = int(inference_steps)
        if not 1 <= steps_value <= 200:
            errors.append("Inference steps should be between 1 and 200.")
    except ValueError:
        errors.append("Inference steps must be an integer.")
        steps_value = 30

    try:
        guidance_value = float(guidance_scale)
        if not 0 <= guidance_value <= 50:
            errors.append("Guidance scale must be between 0 and 50.")
    except ValueError:
        errors.append("Guidance scale must be a number.")
        guidance_value = 7.5

    seed_value: int | None = None
    if seed:
        try:
            seed_value = int(seed)
            if seed_value < 0:
                raise ValueError
        except ValueError:
            errors.append("Seed must be a positive integer.")
            seed_value = None

    allowed_types = {"image/png", "image/jpeg"}
    if image.content_type not in allowed_types:
        errors.append("Upload PNG or JPEG files only.")
    content = await image.read()
    if not content:
        errors.append("Select an image to upload.")
    elif len(content) > settings.max_upload_bytes:
        errors.append("Image exceeds the 8MB upload limit.")

    parameters = {
        "width": width_value,
        "height": height_value,
        "inference_steps": steps_value,
        "guidance_scale": guidance_value,
        "seed": seed_value,
        "model": model,
        "scheduler": scheduler,
    }

    if errors:
        error_messages: list[FlashMessage] = [
            *messages,
            *[_make_flash("error", msg) for msg in errors],
        ]
        cached_user = _session_user_payload(auth)
        validation_context: dict[str, object] = {
            "request": request,
            "messages": error_messages,
            "user": cached_user,
            "prompt_catalog": settings.prompt_catalog,
            "max_upload": settings.max_upload_bytes,
            "form_values": {
                "prompt": prompt,
                "width": width,
                "height": height,
                "inference_steps": inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "model": model,
                "scheduler": scheduler,
            },
        }
        return templates.TemplateResponse(
            "generate.html", validation_context, status_code=status.HTTP_400_BAD_REQUEST
        )

    upload_tuple = (
        image.filename or "upload.png",
        content,
        image.content_type or "image/png",
    )
    try:
        task_payload: GenerationTaskPayload
        tokens: AuthTokens | None
        task_payload, tokens = await gateway.create_generation(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            prompt=prompt_value,
            parameters={
                key: value for key, value in parameters.items() if value is not None
            },
            upload=upload_tuple,
        )
        _merge_auth_session(request, tokens=tokens)
    except BackendError as exc:
        cached_user = _session_user_payload(auth)
        context_messages: list[FlashMessage] = [
            *messages,
            _make_flash("error", exc.message),
        ]
        error_context: dict[str, object] = {
            "request": request,
            "messages": context_messages,
            "user": cached_user,
            "prompt_catalog": settings.prompt_catalog,
            "max_upload": settings.max_upload_bytes,
            "form_values": {
                "prompt": prompt,
                "width": width,
                "height": height,
                "inference_steps": inference_steps,
                "guidance_scale": guidance_scale,
                "seed": seed,
                "model": model,
                "scheduler": scheduler,
            },
        }
        return templates.TemplateResponse(
            "generate.html", error_context, status_code=status.HTTP_400_BAD_REQUEST
        )

    _flash(
        request,
        "success",
        (
            "Generation task queued: "
            f"{task_payload.get('task_id', task_payload.get('id'))}"
        ),
    )
    return RedirectResponse(
        url=request.url_for("history"), status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/history", response_class=HTMLResponse, name="history")
async def history(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
) -> Response | RedirectResponse:
    messages = _consume_flash(request)
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to review task history.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        payload: TaskListPayload
        tokens: AuthTokens | None
        payload, tokens = await gateway.list_tasks(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            page=page,
            page_size=page_size,
        )
        _merge_auth_session(request, tokens=tokens)
    except BackendError as exc:
        context_messages: list[FlashMessage] = [
            *messages,
            {"level": "error", "text": exc.message},
        ]
        error_context: dict[str, object] = {
            "request": request,
            "messages": context_messages,
            "items": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": 0,
                "has_next": False,
            },
        }
        return templates.TemplateResponse(
            "history.html", error_context, status_code=status.HTTP_502_BAD_GATEWAY
        )

    items_value = payload.get("items")
    items: list[JSONValue] = (
        items_value if isinstance(items_value, list) else []
    )
    pagination_value = payload.get("pagination")
    if isinstance(pagination_value, Mapping):
        page_number = pagination_value.get("page")
        page_size_value = pagination_value.get("page_size")
        total_value = pagination_value.get("total")
        has_next_value = pagination_value.get("has_next")
        pagination = {
            "page": page_number if isinstance(page_number, int) else page,
            "page_size": (
                page_size_value if isinstance(page_size_value, int) else page_size
            ),
            "total": total_value if isinstance(total_value, int) else 0,
            "has_next": has_next_value if isinstance(has_next_value, bool) else False,
        }
    else:
        pagination = {
            "page": page,
            "page_size": page_size,
            "total": 0,
            "has_next": False,
        }

    success_context: dict[str, object] = {
        "request": request,
        "messages": messages,
        "items": items,
        "pagination": pagination,
    }
    return templates.TemplateResponse("history.html", success_context)


@app.get("/pricing", response_class=HTMLResponse, name="pricing")
async def pricing_page(request: Request) -> Response:
    context: dict[str, object] = {
        "request": request,
        "messages": _consume_flash(request),
        "plans": _PRICING_PLANS,
    }
    return templates.TemplateResponse("pricing.html", context)


@app.post("/pricing/checkout")
async def pricing_checkout(
    request: Request,
    gateway: BackendGateway = Depends(get_gateway),
    plan_code: str = Form(...),
) -> RedirectResponse:
    auth = _get_auth_session(request)
    if not auth:
        _flash(request, "info", "Sign in to upgrade your workspace.")
        return RedirectResponse(
            url=request.url_for("login_page"), status_code=status.HTTP_303_SEE_OTHER
        )

    payload = {
        "plan_code": plan_code,
        "success_url": str(request.url_for("history")),
        "cancel_url": str(request.url_for("pricing")),
    }

    try:
        response: PaymentPayload
        tokens: AuthTokens | None
        response, tokens = await gateway.create_payment(
            access_token=auth["access_token"],
            refresh_token=auth.get("refresh_token"),
            payload=payload,
        )
        _merge_auth_session(request, tokens=tokens)
    except BackendError as exc:
        _flash(request, "error", exc.message)
        return RedirectResponse(
            url=request.url_for("pricing"), status_code=status.HTTP_303_SEE_OTHER
        )

    confirmation_url = response.get("confirmation_url")
    if confirmation_url:
        return RedirectResponse(
            url=confirmation_url, status_code=status.HTTP_303_SEE_OTHER
        )

    _flash(
        request,
        "success",
        "Payment created. Follow the email instructions to complete your upgrade.",
    )
    return RedirectResponse(
        url=request.url_for("pricing"), status_code=status.HTTP_303_SEE_OTHER
    )


@app.websocket("/ws/tasks/{task_id}")
async def task_updates_ws(
    websocket: WebSocket,
    task_id: str,
    gateway: BackendGateway = Depends(get_gateway),
) -> None:
    await websocket.accept()
    session_data = getattr(websocket, "session", None)
    raw_auth = (
        session_data.get("auth")
        if isinstance(session_data, Mapping)
        else None
    )
    auth = _normalise_auth_session(raw_auth)
    if auth is None:
        await websocket.close(code=4401, reason="Not authenticated")
        return

    user_id = auth.get("user_id")
    access_token = auth.get("access_token")
    if not isinstance(user_id, int) or not isinstance(access_token, str):
        await websocket.close(code=4401, reason="Not authenticated")
        return

    try:
        async for message in gateway.stream_task_updates(
            user_id=user_id,
            task_id=task_id,
            access_token=access_token,
        ):
            await websocket.send_text(message)
    except UnauthorizedError:
        await websocket.close(code=4403, reason="Task stream unauthorized")
    except BackendError as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": exc.message}))
        await websocket.close(
            code=status.WS_1011_INTERNAL_ERROR, reason="Backend error"
        )
    except WebSocketDisconnect:
        return


@app.get("/api/ui/prompt-catalog", response_class=JSONResponse)
async def prompt_catalog() -> JSONResponse:
    return JSONResponse(content={"items": settings.prompt_catalog})


@app.get("/health", response_class=JSONResponse)
async def healthcheck() -> JSONResponse:
    return JSONResponse(content={"status": "ok"})
