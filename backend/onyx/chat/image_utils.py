"""Utilities for resizing images before sending them to LLM providers in chat."""

import base64
import logging
from io import BytesIO

from PIL import Image

logger = logging.getLogger(__name__)

# Match the decompression bomb guard in projects_file_utils.py
Image.MAX_IMAGE_PIXELS = 12_000 * 12_000

# Provider base64 byte limits
_PROVIDER_LIMITS: dict[str, int] = {
    "anthropic": 5 * 1024 * 1024,
    "openai": 20 * 1024 * 1024,
    "google": 20 * 1024 * 1024,
    "vertex_ai": 20 * 1024 * 1024,
}

_DEFAULT_LIMIT: int = 20 * 1024 * 1024

_RESIZE_DIMENSIONS: list[int] = [2048, 1536, 1024]
_QUALITY_STANDARD: int = 85
_QUALITY_FALLBACK: int = 60
_SAFETY_MARGIN: float = 0.95


def get_provider_image_limit(model_provider: str) -> int:
    """Return the base64 byte limit for a given provider string.

    Matches by checking if a known provider key appears in the provider string
    (case-insensitive). Returns a conservative 20 MB default for unknown providers.
    """
    provider_lower = model_provider.lower()
    for key, limit in _PROVIDER_LIMITS.items():
        if key in provider_lower:
            return limit
    return _DEFAULT_LIMIT


def resize_image_for_chat(image_data: bytes, max_base64_bytes: int) -> bytes:
    """Resize an image so its base64 encoding stays under the provider limit.

    If the image already fits, the original bytes object is returned unchanged.
    Otherwise the image is iteratively resized at decreasing dimensions until it
    fits, with a final fallback to 768 px at JPEG quality 60.
    """
    # base64 inflates by ~4/3; apply a 5% safety margin
    max_raw_bytes: int = int(max_base64_bytes * 3 / 4 * _SAFETY_MARGIN)

    logger.info(
        "image_utils: input=%d bytes, limit=%d bytes (base64 limit=%d)",
        len(image_data), max_raw_bytes, max_base64_bytes,
    )

    if len(image_data) <= max_raw_bytes:
        logger.info("image_utils: image fits, no resize needed")
        return image_data

    logger.info("image_utils: image exceeds limit, resizing")

    with Image.open(BytesIO(image_data)) as img:
        logger.info(
            "image_utils: original dimensions=%s mode=%s",
            img.size, img.mode,
        )

        # Handle RGBA: composite onto white background
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        for dim in _RESIZE_DIMENSIONS:
            resized = img.copy()
            resized.thumbnail((dim, dim), Image.Resampling.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="JPEG", quality=_QUALITY_STANDARD)
            result = buf.getvalue()
            logger.info(
                "image_utils: tried %dpx → %d bytes (limit %d) %s",
                dim, len(result), max_raw_bytes,
                "FITS" if len(result) <= max_raw_bytes else "too large",
            )
            if len(result) <= max_raw_bytes:
                return result

        # Final fallback: smallest dimension + lowest quality
        resized = img.copy()
        resized.thumbnail((768, 768), Image.Resampling.LANCZOS)
        buf = BytesIO()
        resized.save(buf, format="JPEG", quality=_QUALITY_FALLBACK)
        result = buf.getvalue()
        logger.warning(
            "image_utils: fallback 768px q60 → %d bytes (limit %d)",
            len(result), max_raw_bytes,
        )
        return result
