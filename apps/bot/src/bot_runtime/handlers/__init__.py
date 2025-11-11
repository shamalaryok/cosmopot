"""Handlers registered with the Telegram bot dispatcher."""

from __future__ import annotations

from collections.abc import Iterable

from aiogram import Router

from . import commands

__all__ = ["get_routers"]


def get_routers() -> Iterable[Router]:
    """Return all routers that should be attached to the dispatcher."""

    return (commands.router,)
