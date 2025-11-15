from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable
from pathlib import Path
from typing import Final

from fastapi import APIRouter

__all__ = ["load_routers"]

_ROUTES_PACKAGE: Final[str] = __name__


def load_routers() -> Iterable[APIRouter]:
    """Discover and yield all routers defined in the routes package."""

    package_path = Path(__file__).resolve().parent

    for module_info in pkgutil.iter_modules([str(package_path)]):
        if module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f"{_ROUTES_PACKAGE}.{module_info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            yield router
