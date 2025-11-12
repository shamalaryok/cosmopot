"""SLA monitoring and synthetic checks API routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from backend.core.config import Settings, get_settings
from backend.observability import get_synthetic_monitor, run_sla_check

router = APIRouter(prefix="/sla", tags=["sla"])
logger = structlog.get_logger(__name__)


@router.get("/status", summary="Get SLA compliance status")
async def sla_status(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    """Get current SLA compliance status."""

    try:
        sla_result = await run_sla_check()

        return {
            "status": "compliant" if sla_result["sla_met"] else "non_compliant",
            "availability_percent": sla_result["availability"] * 100,
            "avg_response_time_seconds": sla_result["avg_response_time"],
            "target_availability": 99.5,
            "target_response_time": 1.0,
            "total_checks": sla_result["total_checks"],
            "successful_checks": sla_result["successful_checks"],
            "timestamp": sla_result["timestamp"],
            "details": sla_result["details"] if settings.debug else [],
        }

    except Exception as e:
        logger.error("sla_check_failed", error=str(e))
        return {
            "status": "error",
            "error": "Failed to perform SLA check",
        }


@router.get("/uptime", summary="Get uptime check results")
async def uptime_status(
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    """Get uptime check results for all endpoints."""

    try:
        monitor = await get_synthetic_monitor()
        results = await monitor.run_checks()

        return {
            "endpoints": results,
            "summary": {
                "total": len(results),
                "up": sum(1 for r in results if r["success"]),
                "down": sum(1 for r in results if not r["success"]),
            },
            "timestamp": results[0]["timestamp"] if results else None,
        }

    except Exception as e:
        logger.error("uptime_check_failed", error=str(e))
        return {
            "error": "Failed to perform uptime checks",
        }
