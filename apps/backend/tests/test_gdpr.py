from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import GDPRSettings, S3Settings, Settings
from backend.security.gdpr import (
    ExportUserDataPayload,
    GDPRDataExporter,
    MarkUserForDeletionPayload,
    PurgeOldAssetsPayload,
)


@pytest.fixture
def gdpr_settings() -> GDPRSettings:
    """Provide GDPR settings."""
    return GDPRSettings(
        input_retention_days=7,
        result_retention_days=90,
        purge_schedule="0 1 * * *",
    )


@pytest.fixture
def s3_settings() -> S3Settings:
    """Provide S3 settings."""
    from pydantic import SecretStr

    return S3Settings.model_construct(
        bucket="test-bucket",
        region="us-east-1",
        endpoint_url="http://localhost:9000",
        access_key_id=SecretStr("test-key"),
        secret_access_key=SecretStr("test-secret"),
        presign_ttl_seconds=1800,
    )


@pytest.fixture
def mock_settings(gdpr_settings: GDPRSettings, s3_settings: S3Settings) -> Settings:
    """Provide mock settings."""
    settings = MagicMock(spec=Settings)
    settings.gdpr = gdpr_settings
    settings.s3 = s3_settings
    return settings


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [uuid.uuid4(), 42])
async def test_export_user_data(
    mock_settings: Settings, user_id: uuid.UUID | int
) -> None:
    """Test user data export."""
    with patch("boto3.client") as mock_boto3:
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3

        exporter = GDPRDataExporter(mock_settings)

        result: ExportUserDataPayload = await exporter.export_user_data(user_id)

        assert result["status"] == "scheduled"
        assert result["user_id"] == str(user_id)
        assert isinstance(result["export_location"], str)
        assert isinstance(result["timestamp"], str)

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert "gdpr-exports" in call_kwargs["Key"]


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [uuid.uuid4(), 84])
async def test_mark_user_for_deletion(
    mock_settings: Settings, user_id: uuid.UUID | int
) -> None:
    """Test marking user for deletion."""
    with patch("boto3.client"):
        exporter = GDPRDataExporter(mock_settings)

        result: MarkUserForDeletionPayload = await exporter.mark_user_for_deletion(
            user_id
        )

        assert result["status"] == "scheduled"
        assert result["user_id"] == str(user_id)
        assert result["hard_delete_after_days"] == 90
        assert isinstance(result["deletion_scheduled_at"], str)


@pytest.mark.asyncio
async def test_purge_old_assets(mock_settings: Settings) -> None:
    """Test purging old S3 assets."""
    with patch("boto3.client") as mock_boto3:
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3

        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator

        import datetime as dt

        old_time = dt.datetime.now(dt.UTC) - dt.timedelta(days=100)
        new_time = dt.datetime.now(dt.UTC)

        mock_paginator.paginate.return_value = [
            {
                "Contents": [
                    {"Key": "old-file-1.txt", "LastModified": old_time},
                    {"Key": "new-file-1.txt", "LastModified": new_time},
                    {"Key": "old-file-2.txt", "LastModified": old_time},
                ]
            }
        ]

        exporter = GDPRDataExporter(mock_settings)
        result: PurgeOldAssetsPayload = await exporter.purge_old_assets(90)

        assert result["status"] == "completed"
        assert result["deleted_count"] == 2
        assert isinstance(result["cutoff_time"], str)


@pytest.mark.asyncio
async def test_purge_old_assets_uses_default_retention(
    mock_settings: Settings,
) -> None:
    """Test that purge uses default retention days when not specified."""
    with patch("boto3.client") as mock_boto3:
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3

        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{"Contents": []}]

        exporter = GDPRDataExporter(mock_settings)
        result: PurgeOldAssetsPayload = await exporter.purge_old_assets(
            older_than_days=None
        )

        assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_export_handles_s3_errors(mock_settings: Settings) -> None:
    """Test that export handles S3 errors gracefully."""
    with patch("boto3.client") as mock_boto3:
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3
        mock_s3.put_object.side_effect = Exception("S3 error")

        exporter = GDPRDataExporter(mock_settings)
        user_id = uuid.uuid4()

        with pytest.raises(RuntimeError, match="Failed to schedule data export"):
            await exporter.export_user_data(user_id)


@pytest.mark.asyncio
async def test_purge_handles_s3_errors(mock_settings: Settings) -> None:
    """Test that purge handles S3 errors gracefully."""
    with patch("boto3.client") as mock_boto3:
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3
        mock_s3.get_paginator.side_effect = Exception("S3 error")

        exporter = GDPRDataExporter(mock_settings)

        with pytest.raises(RuntimeError, match="Failed to purge S3 assets"):
            await exporter.purge_old_assets(90)
