"""Synthetic monitoring and uptime checks."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from prometheus_client import Counter, Gauge, Histogram

from backend.core.config import Settings, get_settings
from backend.observability import add_breadcrumb

logger = structlog.get_logger(__name__)

# Synthetic monitoring metrics
UPTIME_CHECK_SUCCESS = Counter(
    "uptime_check_success_total",
    "Total number of successful uptime checks",
    ["endpoint", "region"]
)

UPTIME_CHECK_FAILURE = Counter(
    "uptime_check_failure_total",
    "Total number of failed uptime checks",
    ["endpoint", "region", "error_type"]
)

UPTIME_CHECK_DURATION = Histogram(
    "uptime_check_duration_seconds",
    "Duration of uptime checks",
    ["endpoint", "region"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf")]
)

UPTIME_CHECK_STATUS = Gauge(
    "uptime_check_status",
    "Status of uptime checks (1=up, 0=down)",
    ["endpoint", "region"]
)


class SyntheticMonitor:
    """Synthetic monitoring service for uptime checks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            follow_redirects=True,
        )
        self.endpoints = [
            {
                "name": "api_health",
                "url": f"{settings.backend_base_url}/health",
                "method": "GET",
                "expected_status": 200,
                "interval": 30,  # seconds
            },
            {
                "name": "api_detailed_health",
                "url": f"{settings.backend_base_url}/health/detailed",
                "method": "GET",
                "expected_status": 200,
                "interval": 60,
            },
            {
                "name": "api_docs",
                "url": f"{settings.backend_base_url}/docs",
                "method": "GET",
                "expected_status": 200,
                "interval": 300,  # 5 minutes
            },
        ]

    async def check_endpoint(self, endpoint: dict[str, Any]) -> dict[str, Any]:
        """Perform a single endpoint check."""
        endpoint_name = endpoint["name"]
        url = endpoint["url"]
        method = endpoint.get("method", "GET")
        expected_status = endpoint.get("expected_status", 200)
        region = self.settings.environment.value

        start_time = time.time()
        result = {
            "endpoint": endpoint_name,
            "url": url,
            "method": method,
            "timestamp": datetime.now(UTC).isoformat(),
            "success": False,
            "response_time": 0,
            "status_code": None,
            "error": None,
        }

        try:
            add_breadcrumb(
                category="synthetic_monitoring",
                message=f"Checking endpoint {endpoint_name}",
                level="info"
            )

            response = await self.client.request(method, url)
            response_time = time.time() - start_time
            
            result.update({
                "response_time": response_time,
                "status_code": response.status_code,
                "success": response.status_code == expected_status,
            })

            # Record metrics
            UPTIME_CHECK_DURATION.labels(
                endpoint=endpoint_name,
                region=region
            ).observe(response_time)

            if result["success"]:
                UPTIME_CHECK_SUCCESS.labels(
                    endpoint=endpoint_name,
                    region=region
                ).inc()
                UPTIME_CHECK_STATUS.labels(
                    endpoint=endpoint_name,
                    region=region
                ).set(1)
            else:
                UPTIME_CHECK_FAILURE.labels(
                    endpoint=endpoint_name,
                    region=region,
                    error_type="status_code"
                ).inc()
                UPTIME_CHECK_STATUS.labels(
                    endpoint=endpoint_name,
                    region=region
                ).set(0)

        except httpx.TimeoutException:
            response_time = time.time() - start_time
            result.update({
                "response_time": response_time,
                "error": "timeout",
            })
            
            UPTIME_CHECK_FAILURE.labels(
                endpoint=endpoint_name,
                region=region,
                error_type="timeout"
            ).inc()
            UPTIME_CHECK_STATUS.labels(
                endpoint=endpoint_name,
                region=region
            ).set(0)

        except Exception as e:
            response_time = time.time() - start_time
            result.update({
                "response_time": response_time,
                "error": str(e),
            })
            
            UPTIME_CHECK_FAILURE.labels(
                endpoint=endpoint_name,
                region=region,
                error_type="exception"
            ).inc()
            UPTIME_CHECK_STATUS.labels(
                endpoint=endpoint_name,
                region=region
            ).set(0)

            logger.error("uptime_check_failed", endpoint=endpoint_name, error=str(e))

        return result

    async def run_checks(self) -> list[dict[str, Any]]:
        """Run all endpoint checks."""
        tasks = [self.check_endpoint(endpoint) for endpoint in self.endpoints]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and return valid results
        valid_results: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                logger.error("uptime_check_exception", error=str(result))
            elif isinstance(result, dict):
                valid_results.append(result)
        
        return valid_results

    async def start_monitoring(self) -> None:
        """Start continuous monitoring."""
        logger.info("starting_synthetic_monitoring")
        
        while True:
            try:
                results = await self.run_checks()
                
                # Log any failures
                failures = [r for r in results if not r["success"]]
                if failures:
                    logger.warning(
                        "uptime_check_failures",
                        failures=len(failures),
                        details=failures
                    )

                # Calculate next check interval (minimum of all intervals)
                intervals = [
                    ep["interval"]
                    for ep in self.endpoints
                    if "interval" in ep and isinstance(ep["interval"], (int, float))
                ]
                min_interval = min(intervals) if intervals else 60
                await asyncio.sleep(min_interval)
                
            except Exception as e:
                logger.error("synthetic_monitoring_error", error=str(e))
                await asyncio.sleep(60)  # Wait 1 minute before retrying

    async def stop(self) -> None:
        """Stop monitoring and cleanup."""
        await self.client.aclose()


# Global monitor instance
_monitor: SyntheticMonitor | None = None


async def get_synthetic_monitor() -> SyntheticMonitor:
    """Get or create synthetic monitor instance."""
    global _monitor
    if _monitor is None:
        settings = get_settings()
        _monitor = SyntheticMonitor(settings)
    return _monitor


async def run_sla_check() -> dict[str, Any]:
    """Run SLA compliance check."""
    monitor = await get_synthetic_monitor()
    results = await monitor.run_checks()
    
    total_checks = len(results)
    successful_checks = sum(1 for r in results if r["success"])
    availability = successful_checks / total_checks if total_checks > 0 else 0
    
    # Calculate average response time
    response_times = [r["response_time"] for r in results if r["response_time"] > 0]
    avg_response_time = (
        sum(response_times) / len(response_times) if response_times else 0
    )

    sla_met = availability >= 0.995 and avg_response_time <= 1.0

    sla_result = {
        "timestamp": datetime.now(UTC).isoformat(),
        "availability": availability,
        "avg_response_time": avg_response_time,
        "total_checks": total_checks,
        "successful_checks": successful_checks,
        "sla_met": sla_met,
        "details": results,
    }

    # 99.5% uptime, <1s average response
    add_breadcrumb(
        category="sla",
        message=(
            f"SLA check: {availability:.2%} availability, "
            f"{avg_response_time:.2f}s avg response"
        ),
        level="info" if sla_result["sla_met"] else "warning",
    )

    return sla_result


# Background task for synthetic monitoring
async def synthetic_monitoring_task() -> None:
    """Background task for synthetic monitoring."""
    try:
        monitor = await get_synthetic_monitor()
        await monitor.start_monitoring()
    except Exception as e:
        logger.error("synthetic_monitoring_task_failed", error=str(e))