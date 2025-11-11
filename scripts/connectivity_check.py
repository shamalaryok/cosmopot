#!/usr/bin/env python3
"""Simple verification script for the docker compose developer stack."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("DEVSTACK_BASE_URL", "http://localhost:8080")
TIMEOUT = float(os.environ.get("DEVSTACK_TIMEOUT", "3"))
RETRIES = int(os.environ.get("DEVSTACK_RETRIES", "15"))


def _request(path: str) -> tuple[int, bytes]:
    url = f"{BASE_URL.rstrip('/')}{path}"
    req = Request(url, headers={"User-Agent": "devstack-health-check"})
    with urlopen(req, timeout=TIMEOUT) as response:  # nosec: trusted local network call
        return response.status, response.read()


def wait_for(path: str, validator: Callable[[int, bytes], bool], label: str) -> None:
    for attempt in range(1, RETRIES + 1):
        try:
            status, body = _request(path)
        except (HTTPError, URLError) as exc:
            if attempt == RETRIES:
                raise RuntimeError(f"{label} did not respond: {exc}") from exc
            time.sleep(2)
            continue

        if validator(status, body):
            print(f"[ok] {label} responded with status {status}")
            return

        if attempt == RETRIES:
            raise RuntimeError(f"{label} returned unexpected payload: {body!r}")
        time.sleep(2)


def backend_validator(status: int, body: bytes) -> bool:
    if status != 200:
        return False
    data = json.loads(body.decode("utf-8"))
    return data.get("status") in {"ok", "degraded"}


def json_status_validator(expected_status: int) -> Callable[[int, bytes], bool]:
    def _inner(status: int, body: bytes) -> bool:
        if status != expected_status:
            return False
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return False
        return bool(payload)

    return _inner


def plain_text_validator(expected_status: int = 200) -> Callable[[int, bytes], bool]:
    def _inner(status: int, body: bytes) -> bool:
        return status == expected_status and body.strip() != b""

    return _inner


def html_validator(expected_status: int = 200) -> Callable[[int, bytes], bool]:
    def _inner(status: int, body: bytes) -> bool:
        return status in {expected_status, 302} and b"<html" in body.lower()

    return _inner


def main() -> int:
    checks = [
        ("/api/health", backend_validator, "Backend"),
        ("/grafana/api/health", json_status_validator(200), "Grafana"),
        ("/prometheus/-/healthy", plain_text_validator(200), "Prometheus"),
        ("/minio/", html_validator(200), "MinIO Console"),
    ]

    for path, validator, label in checks:
        wait_for(path, validator, label)

    print("All connectivity checks completed successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as err:
        print(f"[error] {err}", file=sys.stderr)
        raise SystemExit(1) from err
