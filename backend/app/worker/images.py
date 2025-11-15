from __future__ import annotations

import io

from PIL import Image


class ImageProcessingError(RuntimeError):
    """Raised when thumbnail generation fails."""


def generate_thumbnail(
    image_bytes: bytes,
    *,
    size: tuple[int, int] = (320, 320),
    image_format: str = "JPEG",
) -> bytes:
    """Generate a thumbnail for the provided image bytes."""

    try:
        with Image.open(io.BytesIO(image_bytes)) as original:
            rgb = original.convert("RGB")
            rgb.thumbnail(size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            rgb.save(buffer, format=image_format, optimize=True)
            return buffer.getvalue()
    except Exception as exc:
        raise ImageProcessingError("Unable to generate thumbnail") from exc
