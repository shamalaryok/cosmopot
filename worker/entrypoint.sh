#!/usr/bin/env bash
set -euo pipefail

if command -v python > /dev/null 2>&1; then
  python - <<'PY'
import asyncio
import os
import sys

async def main() -> None:
    host = os.environ.get("CELERY_WAIT_FOR_HOST")
    port = int(os.environ.get("CELERY_WAIT_FOR_PORT", "0"))
    if not host or not port:
        return
    for _ in range(30):
        try:
            reader, writer = await asyncio.open_connection(host, port)
        except Exception:
            await asyncio.sleep(1)
        else:
            writer.close()
            await writer.wait_closed()
            return
    sys.exit("Timed out waiting for dependency")

asyncio.run(main())
PY
fi

exec "$@"
