"""Backend service application package."""

from .app import create_app  # type: ignore[attr-defined]

__all__ = ["create_app"]
