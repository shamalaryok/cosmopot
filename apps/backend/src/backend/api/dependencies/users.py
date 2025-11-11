from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.dependencies import get_db_session
from user_service.enums import UserRole
from user_service.models import User
from user_service.repository import get_user_with_related


async def get_current_user(
    session: AsyncSession = Depends(get_db_session),
    current_user_id: int = Header(
        ...,
        alias="X-User-Id",
        convert_underscores=False,
        description="Authenticated user identifier",
    ),
) -> User:
    user = await get_user_with_related(session, current_user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user not found",
        )
    if not user.is_active or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive or deleted"
        )
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role is not UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required"
        )
    return current_user


async def get_user_from_path(
    user_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> User:
    user = await get_user_with_related(session, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user
