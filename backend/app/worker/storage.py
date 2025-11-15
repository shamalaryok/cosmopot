from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import urlparse

from .config import WorkerSettings


class StorageError(RuntimeError):
    """Raised when S3 interactions fail."""


class StorageClient(Protocol):
    async def download(self, bucket: str, key: str) -> bytes: ...

    async def upload(
        self, bucket: str, key: str, data: bytes, content_type: str
    ) -> str: ...


class MinioObject(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class MinioLike(Protocol):
    def get_object(self, bucket: str, key: str) -> MinioObject: ...

    def put_object(
        self,
        bucket: str,
        key: str,
        data: io.BytesIO,
        length: int,
        content_type: str,
    ) -> None: ...


@dataclass(slots=True)
class S3Location:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def parse_s3_url(url: str) -> S3Location:
    parsed = urlparse(url)
    if parsed.scheme != "s3" or not parsed.netloc:
        raise StorageError("Expected s3:// URL with bucket and key")
    key = parsed.path.lstrip("/")
    if not key:
        raise StorageError("S3 key cannot be empty")
    return S3Location(bucket=parsed.netloc, key=key)


class MinioStorage(StorageClient):
    """Async-friendly wrapper around the MinIO client."""

    def __init__(self, client: MinioLike) -> None:
        self._client: MinioLike = client

    @classmethod
    def from_settings(cls, settings: WorkerSettings) -> MinioStorage:
        if not settings.s3_endpoint:
            raise StorageError("S3 endpoint is not configured")
        from minio import Minio

        parsed = urlparse(settings.s3_endpoint)
        secure = parsed.scheme == "https"
        endpoint = parsed.netloc or parsed.path
        client = cast(
            MinioLike,
            Minio(
                endpoint,
                access_key=settings.s3_access_key,
                secret_key=settings.s3_secret_key,
                secure=secure,
                region=settings.s3_region,
            ),
        )
        return cls(client)

    async def download(self, bucket: str, key: str) -> bytes:
        def _download() -> bytes:
            response: MinioObject = self._client.get_object(bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_download)
        except Exception as exc:  # pragma: no cover - network errors
            raise StorageError(str(exc)) from exc

    async def upload(
        self, bucket: str, key: str, data: bytes, content_type: str
    ) -> str:
        stream = io.BytesIO(data)
        length = len(data)

        def _upload() -> None:
            self._client.put_object(
                bucket,
                key,
                stream,
                length,
                content_type=content_type,
            )

        try:
            await asyncio.to_thread(_upload)
        except Exception as exc:  # pragma: no cover - network errors
            raise StorageError(str(exc)) from exc
        return f"s3://{bucket}/{key}"


class InMemoryStorage(StorageClient):
    """Simple in-memory storage used in tests."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def download(self, bucket: str, key: str) -> bytes:
        try:
            return self._objects[f"{bucket}/{key}"]
        except KeyError as exc:
            raise StorageError("object not found") from exc

    async def upload(
        self, bucket: str, key: str, data: bytes, content_type: str
    ) -> str:
        self._objects[f"{bucket}/{key}"] = bytes(data)
        return f"s3://{bucket}/{key}"
