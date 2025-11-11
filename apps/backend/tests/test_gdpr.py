from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.core.config import GDPRSettings, S3Settings, Settings
from backend.security.gdpr import GDPRDataExporter


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
    return S3Settings(
        bucket="test-bucket",
        region="us-east-1",
        endpoint_url="http://localhost:9000",
    )


@pytest.fixture
def mock_settings(gdpr_settings: GDPRSettings, s3_settings: S3Settings) -> Settings:
    """Provide mock settings."""
    settings = MagicMock(spec=Settings)
    settings.gdpr = gdpr_settings
    settings.s3 = s3_settings
    settings.s3.access_key_id = MagicMock()
    settings.s3.access_key_id.get_secret_value.return_value = "test-key"
    settings.s3.secret_access_key = MagicMock()
    settings.s3.secret_access_key.get_secret_value.return_value = "test-secret"
    return settings


@pytest.mark.asyncio
async def test_export_user_data(mock_settings: Settings) -> None:
    """Test user data export."""
    with patch("boto3.client") as mock_boto3:
        mock_s3 = MagicMock()
        mock_boto3.return_value = mock_s3

        exporter = GDPRDataExporter(mock_settings)
        user_id = uuid.uuid4()

        result = await exporter.export_user_data(user_id)

        assert result["status"] == "scheduled"
        assert str(user_id) in result["user_id"]
        assert "export_location" in result
        assert "timestamp" in result

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert "gdpr-exports" in call_kwargs["Key"]


@pytest.mark.asyncio
async def test_mark_user_for_deletion(mock_settings: Settings) -> None:
    """Test marking user for deletion."""
    with patch("boto3.client"):
        exporter = GDPRDataExporter(mock_settings)
        user_id = uuid.uuid4()

        result = await exporter.mark_user_for_deletion(user_id)

        assert result["status"] == "scheduled"
        assert str(user_id) in result["user_id"]
        assert result["hard_delete_after_days"] == 90
        assert "deletion_scheduled_at" in result


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
        result = await exporter.purge_old_assets(90)

        assert result["status"] == "completed"
        assert result["deleted_count"] == 2
        assert "cutoff_time" in result


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
        result = await exporter.purge_old_assets(older_than_days=None)

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
