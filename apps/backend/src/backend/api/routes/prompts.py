from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies.users import require_admin
from backend.api.schemas.prompts import PromptListResponse, PromptResponse
from backend.db.dependencies import get_db_session
from user_service.enums import PromptCategory
from user_service.repository import (
    create_prompt,
    get_prompt_by_id,
    get_prompt_by_slug,
    list_prompts,
    update_prompt,
)
from user_service.schemas import PromptCreate, PromptUpdate

router = APIRouter(tags=["prompts"])


@router.get(
    "/api/v1/prompts",
    response_model=PromptListResponse,
    summary="List available prompts",
)
async def list_available_prompts(
    category: PromptCategory | None = Query(
        None,
        description="Optional category filter",
    ),
    session: AsyncSession = Depends(get_db_session),
) -> PromptListResponse:
    prompts = await list_prompts(session, category=category, active_only=True)
    items = [PromptResponse.model_validate(prompt) for prompt in prompts]
    return PromptListResponse(items=items)


@router.get(
    "/api/v1/prompts/{slug}",
    response_model=PromptResponse,
    summary="Retrieve a prompt by slug",
)
async def get_prompt_detail(
    slug: str,
    version: int | None = Query(
        None,
        ge=1,
        description="Optional version number to retrieve",
    ),
    include_inactive: bool = Query(
        False,
        description="Whether to include inactive prompts when no version is specified",
    ),
    session: AsyncSession = Depends(get_db_session),
) -> PromptResponse:
    prompt = await get_prompt_by_slug(
        session,
        slug,
        version=version,
        active_only=False if version is not None else not include_inactive,
    )
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )
    if version is None and not include_inactive and not prompt.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )
    return PromptResponse.model_validate(prompt)


@router.post(
    "/api/v1/admin/prompts",
    response_model=PromptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a prompt or new version",
    tags=["prompts", "admin"],
)
async def create_prompt_version(
    payload: PromptCreate,
    session: AsyncSession = Depends(get_db_session),
    _: object = Depends(require_admin),
) -> PromptResponse:
    try:
        prompt = await create_prompt(session, payload)
    except ValueError as exc:  # pragma: no cover - validation guard
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await session.commit()
    await session.refresh(prompt)
    return PromptResponse.model_validate(prompt)


@router.patch(
    "/api/v1/admin/prompts/{prompt_id}",
    response_model=PromptResponse,
    summary="Update prompt metadata",
    tags=["prompts", "admin"],
)
async def update_prompt_metadata(
    prompt_id: int,
    payload: PromptUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: object = Depends(require_admin),
) -> PromptResponse:
    prompt = await get_prompt_by_id(session, prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    try:
        updated = await update_prompt(session, prompt, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    await session.commit()
    await session.refresh(updated)
    return PromptResponse.model_validate(updated)


@router.delete(
    "/api/v1/admin/prompts/{prompt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete a prompt version",
    tags=["prompts", "admin"],
)
async def deactivate_prompt_version(
    prompt_id: int,
    session: AsyncSession = Depends(get_db_session),
    _: object = Depends(require_admin),
) -> Response:
    prompt = await get_prompt_by_id(session, prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
        )

    if prompt.is_active:
        await update_prompt(session, prompt, PromptUpdate(is_active=False))
        await session.commit()
    else:
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
