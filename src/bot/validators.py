"""Validation helpers for user-provided files."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from .constants import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIME_TYPES,
    MAX_IMAGE_SIZE_BYTES,
)
from .exceptions import InvalidFileError

_MAX_SIZE_HUMAN: Final[str] = "10 MB"


def human_readable_size(size_in_bytes: int) -> str:
    """Convert a size in bytes into a human-readable string."""

    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    if size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    return f"{size_in_bytes / (1024 * 1024):.1f} MB"


def validate_image(
    *, file_name: str | None, file_size: int | None, mime_type: str | None
) -> None:
    """Validate that the provided file looks like a supported image.

    Args:
        file_name: Name of the uploaded file (may be ``None`` for Telegram photos).
        file_size: Reported size in bytes. Must not exceed 10 MB.
        mime_type: Optional MIME type reported by Telegram.

    Raises:
        InvalidFileError: If the file is too large or not a supported type.
    """

    if file_size is None:
        raise InvalidFileError(
            "Unable to determine file size. Please re-upload the image."
        )

    if file_size > MAX_IMAGE_SIZE_BYTES:
        raise InvalidFileError(
            "The image is larger than 10 MB. Please upload a smaller JPEG or PNG file."
        )

    if mime_type and mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise InvalidFileError(
            "Unsupported file type. Only JPEG and PNG images are allowed."
        )

    if file_name:
        extension = Path(file_name).suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_IMAGE_EXTENSIONS))
            raise InvalidFileError(
                f"Unsupported extension '{extension}'. Allowed extensions: {allowed}."
            )
