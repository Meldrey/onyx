"""Tests for chat image resize utilities."""

import base64
from io import BytesIO

from PIL import Image
from PIL import ImageDraw

from onyx.chat.image_utils import get_provider_image_limit
from onyx.chat.image_utils import resize_image_for_chat


def _make_jpeg_bytes(width: int, height: int, fill: str = "red") -> bytes:
    """Create a JPEG image of the given size and return its raw bytes."""
    img = Image.new("RGB", (width, height), fill)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _make_large_jpeg_bytes(width: int, height: int) -> bytes:
    """Create a large JPEG with noisy content to prevent high compression."""
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    # Draw many small rectangles with varying colors to defeat compression
    for x in range(0, width, 4):
        for y in range(0, height, 4):
            color = ((x * 7 + y * 13) % 256, (x * 11 + y * 3) % 256, (y * 17 + x) % 256)
            draw.rectangle([x, y, x + 3, y + 3], fill=color)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=98)
    return buf.getvalue()


class TestGetProviderImageLimit:
    """Tests for get_provider_image_limit."""

    def test_anthropic_limit(self) -> None:
        assert get_provider_image_limit("anthropic") == 5 * 1024 * 1024

    def test_openai_limit(self) -> None:
        assert get_provider_image_limit("openai") == 20 * 1024 * 1024

    def test_google_limit(self) -> None:
        assert get_provider_image_limit("google") == 20 * 1024 * 1024

    def test_vertex_ai_limit(self) -> None:
        assert get_provider_image_limit("vertex_ai") == 20 * 1024 * 1024

    def test_case_insensitive(self) -> None:
        assert get_provider_image_limit("Anthropic") == 5 * 1024 * 1024
        assert get_provider_image_limit("OPENAI") == 20 * 1024 * 1024

    def test_unknown_provider_returns_default(self) -> None:
        assert get_provider_image_limit("some_unknown_provider") == 5 * 1024 * 1024

    def test_provider_substring_match(self) -> None:
        """Provider key can appear anywhere in the string."""
        assert get_provider_image_limit("my-anthropic-proxy") == 5 * 1024 * 1024


class TestResizeImageForChat:
    """Tests for resize_image_for_chat."""

    def test_small_image_passes_through_unchanged(self) -> None:
        """An image well under the limit is returned as the same object."""
        image_data = _make_jpeg_bytes(100, 100)
        limit = 20 * 1024 * 1024  # 20 MB — way above the tiny image
        result = resize_image_for_chat(image_data, limit)
        assert result is image_data

    def test_large_image_is_resized(self) -> None:
        """An image over the limit is resized and the base64 fits."""
        image_data = _make_large_jpeg_bytes(4000, 3000)
        # Set a tight limit that forces resize
        limit = len(base64.b64encode(image_data)) // 4
        result = resize_image_for_chat(image_data, limit)
        assert len(base64.b64encode(result)) <= limit
        assert result is not image_data

    def test_rgba_image_does_not_crash(self) -> None:
        """RGBA images are handled without error and produce valid output."""
        img = Image.new("RGBA", (2000, 2000), (255, 0, 0, 128))
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_data = buf.getvalue()
        # Force resize with a small limit
        limit = 1024
        result = resize_image_for_chat(image_data, limit)
        # Verify the output is a valid JPEG
        with Image.open(BytesIO(result)) as out:
            assert out.format == "JPEG"

    def test_palette_mode_converts(self) -> None:
        """Palette (P) mode images convert successfully."""
        img = Image.new("P", (2000, 2000))
        # Draw varied content so PNG doesn't compress to near-zero
        draw = ImageDraw.Draw(img)
        for x in range(0, 2000, 8):
            for y in range(0, 2000, 8):
                draw.rectangle([x, y, x + 7, y + 7], fill=(x * y) % 256)
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_data = buf.getvalue()
        limit = 1024
        result = resize_image_for_chat(image_data, limit)
        with Image.open(BytesIO(result)) as out:
            assert out.format == "JPEG"

    def test_grayscale_mode_converts(self) -> None:
        """Grayscale (L) mode images convert successfully."""
        img = Image.new("L", (2000, 2000), 128)
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_data = buf.getvalue()
        limit = 1024
        result = resize_image_for_chat(image_data, limit)
        with Image.open(BytesIO(result)) as out:
            assert out.format == "JPEG"

    def test_image_exactly_at_limit_passes_through(self) -> None:
        """An image whose raw bytes exactly equal the raw threshold passes through."""
        image_data = _make_jpeg_bytes(100, 100)
        # Compute the limit such that max_raw_bytes == len(image_data)
        # max_raw_bytes = int(limit * 3/4 * 0.95), so limit = len / (3/4 * 0.95)
        limit = int(len(image_data) / (3 / 4 * 0.95)) + 1
        result = resize_image_for_chat(image_data, limit)
        assert result is image_data
