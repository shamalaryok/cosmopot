from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, ClassVar, cast

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

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Wrap the class __init__ to handle metadata argument transformation."""
        super().__init_subclass__(**kwargs)
        original_init = cast(Callable[..., None], cls.__init__)

        if getattr(original_init, "__metadata_alias_wrapped__", False):
            return

        @wraps(original_init)
        def wrapped_init(self: Any, *args: Any, **init_kwargs: Any) -> None:
            metadata_value = init_kwargs.pop(
                "metadata",
                cls._metadata_marker,
            )
            if (
                metadata_value is not cls._metadata_marker
                and "meta_data" not in init_kwargs
            ):
                init_kwargs["meta_data"] = cls._coerce_metadata(metadata_value)
            original_init(self, *args, **init_kwargs)

        wrapped_init.__metadata_alias_wrapped__ = True
        cls.__init__ = wrapped_init

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
