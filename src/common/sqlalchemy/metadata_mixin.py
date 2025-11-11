from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

__all__ = ["MetadataAliasMixin"]


class MetadataAliasMixin:
    """Provide instance-level JSON metadata dict access via metadata_dict property.

    This mixin provides a property `metadata_dict` for accessing the JSON metadata
    from the ``meta_data`` column, while not interfering with SQLAlchemy's
    ``metadata`` class attribute on DeclarativeBase.

    The mixin also supports initializing instances with a ``metadata`` keyword
    argument that will be stored in the ``meta_data`` column for backward
    compatibility.
    """

    meta_data: dict[str, Any]

    _metadata_marker: ClassVar[object] = object()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        metadata_value = kwargs.pop("metadata", self._metadata_marker)
        if metadata_value is not self._metadata_marker and "meta_data" not in kwargs:
            kwargs["meta_data"] = self._coerce_metadata(metadata_value)
        super().__init__(*args, **kwargs)

    @property
    def metadata_dict(self) -> dict[str, Any]:
        """Access the mapped metadata payload with explicit typing."""
        return self.meta_data

    @metadata_dict.setter
    def metadata_dict(self, value: Mapping[str, Any]) -> None:
        self.meta_data = self._coerce_metadata(value)

    @metadata_dict.deleter
    def metadata_dict(self) -> None:
        del self.meta_data

    @staticmethod
    def _coerce_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        raise TypeError("metadata assignments must be mapping types")
