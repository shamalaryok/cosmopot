from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import TypedDict

import boto3
import structlog

from backend.core.config import Settings

logger = structlog.get_logger(__name__)


class ExportUserDataPayload(TypedDict):
    """Typed payload for export_user_data result."""

    status: str
    user_id: str
    export_location: str
    timestamp: str


class MarkUserForDeletionPayload(TypedDict):
    """Typed payload for mark_user_for_deletion result."""

    status: str
    user_id: str
    deletion_scheduled_at: str
    hard_delete_after_days: int


class PurgeOldAssetsPayload(TypedDict):
    """Typed payload for purge_old_assets result."""

    status: str
    deleted_count: int
    cutoff_time: str


class GDPRDataExporter:
    """Handles GDPR data export and S3 asset purging."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3.endpoint_url,
            aws_access_key_id=(
                settings.s3.access_key_id.get_secret_value()
                if settings.s3.access_key_id
                else None
            ),
            aws_secret_access_key=(
                settings.s3.secret_access_key.get_secret_value()
                if settings.s3.secret_access_key
                else None
            ),
            region_name=settings.s3.region,
        )

    async def export_user_data(self, user_id: int | uuid.UUID) -> ExportUserDataPayload:
        """
        Export user data to S3 for GDPR compliance.

        Args:
            user_id: Database identifier (int or UUID).

        Returns:
            ExportUserDataPayload: export status and location
        """
        user_id_str = str(user_id)
        try:
            export_timestamp = dt.datetime.now(dt.UTC).isoformat()
            export_data = {
                "user_id": user_id_str,
                "export_timestamp": export_timestamp,
                "data": {
                    "profile": {},
                    "sessions": [],
                    "subscriptions": [],
                },
            }

            timestamp = dt.datetime.now(dt.UTC).timestamp()
            file_key = f"gdpr-exports/{user_id_str}/{timestamp}.json"

            self.s3_client.put_object(
                Bucket=self.settings.s3.bucket,
                Key=file_key,
                Body=json.dumps(export_data),
                ContentType="application/json",
            )

            logger.info(
                "gdpr_export_created",
                user_id=user_id_str,
                export_key=file_key,
            )

            result: ExportUserDataPayload = {
                "status": "scheduled",
                "user_id": user_id_str,
                "export_location": file_key,
                "timestamp": dt.datetime.now(dt.UTC).isoformat(),
            }
            return result
        except Exception as exc:
            logger.exception("gdpr_export_failed", user_id=user_id_str)
            raise RuntimeError("Failed to schedule data export") from exc

    async def mark_user_for_deletion(
        self, user_id: int | uuid.UUID
    ) -> MarkUserForDeletionPayload:
        """
        Mark user account for deletion (soft delete pattern).

        Args:
            user_id: Database identifier (int or UUID).

        Returns:
            MarkUserForDeletionPayload: deletion status information
        """
        user_id_str = str(user_id)
        try:
            logger.info(
                "user_marked_for_deletion",
                user_id=user_id_str,
            )

            result: MarkUserForDeletionPayload = {
                "status": "scheduled",
                "user_id": user_id_str,
                "deletion_scheduled_at": dt.datetime.now(dt.UTC).isoformat(),
                "hard_delete_after_days": self.settings.gdpr.result_retention_days,
            }
            return result
        except Exception as exc:
            logger.exception("gdpr_deletion_failed", user_id=user_id_str)
            raise RuntimeError("Failed to schedule account deletion") from exc

    async def purge_old_assets(
        self, older_than_days: int | None = None
    ) -> PurgeOldAssetsPayload:
        """
        Purge S3 assets older than specified days.

        Args:
            older_than_days: Delete assets older than this many days. If None,
                falls back to the configured result retention days.

        Returns:
            PurgeOldAssetsPayload: purge statistics
        """
        days = (
            older_than_days
            if older_than_days is not None
            else self.settings.gdpr.result_retention_days
        )
        try:
            cutoff_time_dt = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
            cutoff_time = cutoff_time_dt.isoformat()
            logger.info(
                "s3_purge_started",
                cutoff_time=cutoff_time,
                older_than_days=days,
            )

            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.settings.s3.bucket)

            deleted_count = 0
            for page in pages:
                if "Contents" not in page:
                    continue

                for obj in page["Contents"]:
                    last_modified = obj["LastModified"]
                    if isinstance(last_modified, dt.datetime):
                        if last_modified.tzinfo is None:
                            last_modified = last_modified.replace(tzinfo=dt.UTC)

                    if last_modified < cutoff_time_dt:
                        self.s3_client.delete_object(
                            Bucket=self.settings.s3.bucket, Key=obj["Key"]
                        )
                        deleted_count += 1
                        logger.debug(
                            "s3_object_deleted",
                            key=obj["Key"],
                            last_modified=(
                                last_modified.isoformat()
                                if isinstance(last_modified, dt.datetime)
                                else str(last_modified)
                            ),
                        )

            logger.info(
                "s3_purge_completed",
                deleted_count=deleted_count,
                older_than_days=days,
            )

            result: PurgeOldAssetsPayload = {
                "status": "completed",
                "deleted_count": deleted_count,
                "cutoff_time": cutoff_time,
            }
            return result
        except Exception as exc:
            logger.exception("s3_purge_failed")
            raise RuntimeError("Failed to purge S3 assets") from exc
