"""Unit 7 tests: PlaceholderImageProvider + factory wiring.

Integration tests — Pillow actually runs and generates real JPEG files in a
temp directory. Pixel dimensions are verified by opening the output file.
No mocking of Pillow; that would defeat the purpose of checking the spec math.
"""
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.providers.base import CharacterRef, ImageResult
from app.providers.placeholder_image import (
    PlaceholderImageProvider,
    _DEFAULT_DIMS,
    _SPREAD_DIMS,
)
from app.storage.local import LocalStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provider(tmpdir: str) -> PlaceholderImageProvider:
    return PlaceholderImageProvider(LocalStorage(tmpdir))


def _char_ref() -> CharacterRef:
    return CharacterRef(kind="reference_images", data={"storage_keys": ["ref/bunny.png"]})


def _open_from_storage(storage: LocalStorage, key: str) -> Image.Image:
    return Image.open(__import__("io").BytesIO(storage.get(key)))


# ---------------------------------------------------------------------------
# Return type and storage key format
# ---------------------------------------------------------------------------


class TestReturnShape:
    def test_returns_image_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _provider(tmp).generate_scene("A bunny in a field", _char_ref(), {})
        assert isinstance(result, ImageResult)

    def test_storage_key_starts_with_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _provider(tmp).generate_scene("A bunny", _char_ref(), {})
        assert result.storage_key.startswith("placeholders/")

    def test_storage_key_ends_with_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _provider(tmp).generate_scene("A bunny", _char_ref(), {})
        assert result.storage_key.endswith(".jpg")

    def test_seed_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _provider(tmp).generate_scene("A bunny", _char_ref(), {})
        assert result.seed is None

    def test_provider_params_passed_through(self):
        params = {"spread_type": "VIGNETTE", "scene_index": 3}
        with tempfile.TemporaryDirectory() as tmp:
            result = _provider(tmp).generate_scene("A bunny", _char_ref(), params)
        assert result.provider_params == params

    def test_file_written_to_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorage(tmp)
            provider = PlaceholderImageProvider(storage)
            result = provider.generate_scene("A bunny", _char_ref(), {})
            assert storage.exists(result.storage_key)

    def test_each_call_produces_unique_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _provider(tmp)
            keys = {p.generate_scene("prompt", _char_ref(), {}).storage_key for _ in range(5)}
        assert len(keys) == 5


# ---------------------------------------------------------------------------
# Spread type → pixel dimensions
# ---------------------------------------------------------------------------


class TestSpreadDimensions:
    def _dims(self, spread_type: str) -> tuple[int, int]:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorage(tmp)
            provider = PlaceholderImageProvider(storage)
            result = provider.generate_scene("test prompt", _char_ref(), {"spread_type": spread_type})
            img = _open_from_storage(storage, result.storage_key)
            return img.size  # (width, height)

    def test_full_bleed_double(self):
        assert self._dims("FULL_BLEED_DOUBLE") == (5175, 2625)

    def test_full_bleed_single_with_text_page(self):
        assert self._dims("FULL_BLEED_SINGLE_WITH_TEXT_PAGE") == (2625, 2625)

    def test_full_bleed_single_overlay(self):
        assert self._dims("FULL_BLEED_SINGLE_OVERLAY") == (2625, 2625)

    def test_portrait_with_caption_below(self):
        assert self._dims("PORTRAIT_WITH_CAPTION_BELOW") == (2625, 1838)

    def test_vignette(self):
        assert self._dims("VIGNETTE") == (1838, 1838)

    def test_cover(self):
        assert self._dims("COVER") == (2625, 2625)

    def test_unknown_spread_type_uses_default(self):
        assert self._dims("MADE_UP_TYPE") == _DEFAULT_DIMS

    def test_missing_spread_type_uses_default(self):
        assert self._dims("") == _DEFAULT_DIMS

    def test_spread_dims_table_complete(self):
        # All spread types in the spec are covered.
        expected = {
            "FULL_BLEED_DOUBLE",
            "FULL_BLEED_SINGLE_WITH_TEXT_PAGE",
            "FULL_BLEED_SINGLE_OVERLAY",
            "PORTRAIT_WITH_CAPTION_BELOW",
            "VIGNETTE",
            "COVER",
        }
        assert set(_SPREAD_DIMS.keys()) == expected


# ---------------------------------------------------------------------------
# Image is valid JPEG
# ---------------------------------------------------------------------------


class TestImageFormat:
    def test_output_is_valid_jpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorage(tmp)
            provider = PlaceholderImageProvider(storage)
            result = provider.generate_scene("A rabbit", _char_ref(), {"spread_type": "VIGNETTE"})
            img = _open_from_storage(storage, result.storage_key)
        assert img.format == "JPEG"

    def test_output_is_rgb(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorage(tmp)
            provider = PlaceholderImageProvider(storage)
            result = provider.generate_scene("A rabbit", _char_ref(), {"spread_type": "VIGNETTE"})
            img = _open_from_storage(storage, result.storage_key)
        assert img.mode == "RGB"


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


class TestFactory:
    def test_placeholder_name_returns_placeholder_provider(self):
        mock_settings = MagicMock()
        mock_settings.image_provider = "placeholder"
        mock_settings.storage_local_root = "/tmp/test-storage"
        with patch("app.providers.factory.get_settings", return_value=mock_settings):
            from app.providers.factory import get_image_provider
            provider = get_image_provider()
        assert isinstance(provider, PlaceholderImageProvider)

    def test_fake_name_returns_fake_provider(self):
        from app.providers.fake_image import FakeImageProvider
        mock_settings = MagicMock()
        mock_settings.image_provider = "fake"
        with patch("app.providers.factory.get_settings", return_value=mock_settings):
            from app.providers.factory import get_image_provider
            provider = get_image_provider()
        assert isinstance(provider, FakeImageProvider)

    def test_unknown_name_raises_value_error(self):
        mock_settings = MagicMock()
        mock_settings.image_provider = "leonardo"
        with (
            patch("app.providers.factory.get_settings", return_value=mock_settings),
            pytest.raises(ValueError, match="leonardo"),
        ):
            from app.providers.factory import get_image_provider
            get_image_provider()
