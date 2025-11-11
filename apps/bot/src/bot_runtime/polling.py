from __future__ import annotations

import asyncio

from backend.core.config import get_settings
from backend.core.logging import configure_logging
from bot_runtime.runtime import BotRuntime


async def _run() -> None:
    settings = get_settings()
    configure_logging(settings)

    runtime = BotRuntime(settings)
    await runtime.startup()

    try:
        await runtime.start_polling()
    finally:
        await runtime.shutdown()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
