from __future__ import annotations

import pytest

from bot.exceptions import InvalidFileError
from bot.validators import human_readable_size, validate_image


@pytest.mark.parametrize(
    "size,expected",
    [
        (512, "512 B"),
        (2048, "2.0 KB"),
        (5 * 1024 * 1024, "5.0 MB"),
    ],
)
def test_human_readable_size(size: int, expected: str) -> None:
    assert human_readable_size(size) == expected


@pytest.mark.asyncio
async def test_validate_image_accepts_valid_png() -> None:
    # Should not raise
    validate_image(file_name="image.png", file_size=1024, mime_type="image/png")


@pytest.mark.asyncio
async def test_validate_image_rejects_large_file() -> None:
    with pytest.raises(InvalidFileError) as exc:
        validate_image(
            file_name="image.png", file_size=11 * 1024 * 1024, mime_type="image/png"
        )
    assert "larger than 10 MB" in str(exc.value)


@pytest.mark.asyncio
async def test_validate_image_rejects_unknown_extension() -> None:
    with pytest.raises(InvalidFileError) as exc:
        validate_image(file_name="image.gif", file_size=1024, mime_type="image/gif")
    assert "Only JPEG and PNG images are allowed" in str(exc.value)


@pytest.mark.asyncio
async def test_validate_image_rejects_missing_size() -> None:
    with pytest.raises(InvalidFileError) as exc:
        validate_image(file_name="image.png", file_size=None, mime_type="image/png")
    assert "Unable to determine" in str(exc.value)
