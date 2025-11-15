from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import CHAR, JSON, DateTime, TypeDecorator


class GUID(TypeDecorator[uuid.UUID]):
    """Platform-independent GUID type.

    Uses PostgreSQL's native UUID type when available, otherwise falls back to
    a CHAR(36) representation.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: uuid.UUID | None, dialect: Dialect) -> Any:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return str(value)
        raise TypeError("GUID values must be UUID instances")

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return value
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


JSONValue = dict[str, Any] | list[Any]


class JSONType(TypeDecorator[JSONValue]):
    """JSON wrapper that ensures consistent behaviour across dialects."""

    impl = JSONB
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "sqlite":
            return dialect.type_descriptor(JSON())
        return dialect.type_descriptor(JSONB())

    def process_bind_param(self, value: JSONValue | None, dialect: Dialect) -> Any:
        if value is None:
            return value
        if isinstance(value, (dict, list)):
            serialised = json.loads(json.dumps(value))
            if isinstance(serialised, (dict, list)):
                return serialised
            raise TypeError("JSON serialisation returned unexpected type")
        raise TypeError("JSONType values must be dicts or lists")

    def process_result_value(self, value: Any, dialect: Dialect) -> JSONValue | None:
        if value is None:
            return value
        if isinstance(value, (dict, list)):
            return value
        decoded = json.loads(value)
        if isinstance(decoded, (dict, list)):
            return decoded
        raise TypeError("JSON deserialisation returned unexpected type")


class UTCDateTime(TypeDecorator[dt.datetime]):
    """Timezone-aware datetime type that ensures UTC timezone.

    Uses DateTime(timezone=True) for all dialects but ensures that values
    returned from the database are always timezone-aware (UTC).
    This is particularly important for SQLite which doesn't natively support
    timezone-aware datetimes.
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: dt.datetime | None, dialect: Dialect) -> Any:
        if value is None:
            return value
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                raise ValueError("UTCDateTime requires timezone-aware datetime")
            return value.astimezone(dt.UTC)
        raise TypeError("UTCDateTime values must be datetime instances")

    def process_result_value(self, value: Any, dialect: Dialect) -> dt.datetime | None:
        if value is None:
            return value
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=dt.UTC)
            return value.astimezone(dt.UTC)
        if isinstance(value, str):
            parsed = dt.datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.UTC)
            return parsed.astimezone(dt.UTC)
        raise TypeError(f"Expected datetime, got {type(value)}")
