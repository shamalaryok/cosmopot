from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from fastapi.responses import StreamingResponse

__all__ = ["ExportService"]


class ExportService:
    @staticmethod
    def export_to_csv(data: list[dict[str, Any]], filename: str) -> StreamingResponse:
        if not data:
            output = StringIO()
            output.write("")
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )

        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        output.seek(0)

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @staticmethod
    def export_to_json(data: list[dict[str, Any]], filename: str) -> StreamingResponse:
        json_str = json.dumps(data, indent=2, default=str)

        return StreamingResponse(
            iter([json_str]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
