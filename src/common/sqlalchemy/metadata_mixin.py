from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast, overload

from sqlalchemy import MetaData

__all__ = ["MetadataAliasMixin"]

_T = TypeVar("_T", bound="MetadataAliasMixin")


class _MetadataDescriptor(Generic[_T]):
    """Descriptor that provides class-level MetaData and instance-level dict access."""

    @overload
    def __get__(self, instance: None, owner: type[_T]) -> MetaData: ...

    @overload
    def __get__(
        self,
        instance: _T,
        owner: type[_T] | None = None,
    ) -> dict[str, Any]: ...

    def __get__(
        self,
        instance: _T | None,
        owner: type[_T] | None = None,
    ) -> MetaData | dict[str, Any]:
        if owner is None:
            raise AttributeError("metadata descriptor requires an owning class")
        if instance is None:
            registry = getattr(owner, "registry", None)
            if registry is None:
                raise AttributeError(
                    f"{owner.__name__} must inherit from DeclarativeBase "
                    "to use MetadataAliasMixin"
                )
            return cast(MetaData, registry.metadata)
        return instance.meta_data

    def __set__(self, instance: _T, value: Mapping[str, Any]) -> None:
        instance.meta_data = dict(value)

    def __delete__(self, instance: _T) -> None:
        del instance.meta_data


class MetadataAliasMixin:
    """Provide instance-level JSON access while preserving class-level MetaData.

    This mixin provides a descriptor that allows `metadata` to behave differently
    at class and instance levels:
    - At class level: returns SQLAlchemy's :class:`MetaData`
    - At instance level: returns the JSON metadata dict from the ``meta_data`` column

    For type checking we keep DeclarativeBase's metadata class attribute intact while
    still providing the runtime descriptor behaviour.
    """

    meta_data: dict[str, Any]

    if TYPE_CHECKING:
        # For static type checkers, expose only the SQLAlchemy contract.
        metadata: ClassVar[MetaData]
    else:
        # At runtime, install the descriptor without type annotation
        metadata = _MetadataDescriptor()

    registry: ClassVar[Any]
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
