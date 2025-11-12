from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, ClassVar

from sqlalchemy import MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.db.types import GUID, JSONType, UTCDateTime
from common.sqlalchemy import MetadataAliasMixin

__all__ = [
    "Base",
    "UUIDPrimaryKeyMixin",
    "TimestampMixin",
    "JSONDataMixin",
    "MetadataAliasMixin",
    "metadata",
]

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)



class Base(DeclarativeBase):
    metadata: ClassVar[MetaData]


Base.registry.metadata = metadata


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4, nullable=False
    )


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class JSONDataMixin:
    data: Mapped[dict[str, Any]] = mapped_column(
        JSONType(),
        default=dict,
        nullable=False,
    )
