"""Common database models and utilities."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import Select, func
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Pagination parameters for API endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page",
    )

    @property
    def offset(self) -> int:
        """Calculate offset for SQL queries."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit for SQL queries."""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model."""

    items: list[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


async def paginate_query(
    session: AsyncSession,
    stmt: Select[Any],
    pagination: PaginationParams,
) -> tuple[list[Any], int]:
    """Paginate a SQLAlchemy query and return items with total count."""
    # Get total count
    count_stmt = stmt.order_by(None).with_only_columns(func.count())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Apply pagination and get items
    paginated_stmt = stmt.offset(pagination.offset).limit(pagination.limit)
    result = await session.execute(paginated_stmt)
    items = list(result.scalars().all())

    return items, total
