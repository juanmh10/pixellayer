"""
Background Removal Tests
==========================
Integration tests for the background removal pipeline.
Tests model registry, lazy loading, and RGBA output quality.

NOTE: These tests require model weights to be downloaded.
On first run, models will be fetched from HuggingFace (~1-2GB).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.engine.models.birefnet import create_birefnet_models
from src.engine.models.isnet import create_isnet_model
from src.engine.models.registry import ModelRegistry
from src.engine.models.rmbg import create_rmbg_model
from src.utils.exceptions import ModelNotFoundError


class TestModelRegistry:
    """Test model registry without loading any models."""

    def test_register_and_list(self) -> None:
        reg = ModelRegistry()
        models = create_birefnet_models()
        for m in models:
            reg.register(m)

        listed = reg.list_models()
        assert len(listed) == 4  # 4 BiRefNet variants
        assert all(not m["is_loaded"] for m in listed)

    def test_register_all_models(self) -> None:
        reg = ModelRegistry()
        for m in create_birefnet_models():
            reg.register(m)
        reg.register(create_rmbg_model())
        reg.register(create_isnet_model())

        listed = reg.list_models()
        assert len(listed) == 6

    def test_get_model_info_no_loading(self) -> None:
        reg = ModelRegistry()
        for m in create_birefnet_models():
            reg.register(m)

        info = reg.get_model_info("birefnet-general")
        assert info["model_id"] == "birefnet-general"
        assert info["is_loaded"] is False
        assert "BiRefNet" in info["name"]

    def test_get_unknown_model_raises(self) -> None:
        reg = ModelRegistry()
        with pytest.raises(ModelNotFoundError):
            reg.get("nonexistent-model")

    def test_list_models_does_not_load(self) -> None:
        """Verify that listing models doesn't trigger weight loading."""
        reg = ModelRegistry()
        for m in create_birefnet_models():
            reg.register(m)

        # List multiple times
        for _ in range(10):
            listed = reg.list_models()

        # No model should be loaded
        assert all(not m["is_loaded"] for m in listed)


class TestBaseModelLifecycle:
    """Test lazy loading and TTL behavior."""

    def test_model_starts_unloaded(self) -> None:
        models = create_birefnet_models()
        for model in models:
            assert not model.is_loaded

    def test_get_info_without_loading(self) -> None:
        model = create_birefnet_models()[0]
        info = model.get_info()
        assert info["is_loaded"] is False
        assert "hf_id" in info

    def test_unload_when_not_loaded(self) -> None:
        """Unloading a model that isn't loaded should be a no-op."""
        model = create_birefnet_models()[0]
        model.unload()  # Should not raise
        assert not model.is_loaded


class TestBackgroundRemovalIntegration:
    """Integration tests that actually run model inference.

    These tests are marked as slow because they download and load ML models.
    Skip with: pytest -m "not slow"
    """

    @pytest.fixture
    def test_image(self, tmp_path: Path) -> Path:
        """Create a test image with a simple subject on a colored background."""
        img = Image.new("RGB", (256, 256), color=(50, 150, 255))
        # Draw a simple "subject" in the center
        pixels = img.load()
        for x in range(64, 192):
            for y in range(64, 192):
                pixels[x, y] = (255, 200, 150)  # Skin-like color
        path = tmp_path / "test_subject.png"
        img.save(str(path))
        return path

    @pytest.mark.slow
    def test_birefnet_general_produces_rgba(self, test_image: Path) -> None:
        """Test that BiRefNet general produces valid RGBA output."""
        from src.engine.processors.background import remove_background

        result = remove_background(
            image_path=str(test_image),
            model_id="birefnet-general",
        )

        assert result.success is True
        output = Image.open(result.image.file_path)
        assert output.mode == "RGBA"
        assert output.size == (256, 256)  # Same dimensions as input

    @pytest.mark.slow
    def test_output_has_transparency(self, test_image: Path) -> None:
        """Verify that background pixels have alpha < 255."""
        from src.engine.processors.background import remove_background

        result = remove_background(
            image_path=str(test_image),
            model_id="birefnet-general",
        )

        output = Image.open(result.image.file_path)
        alpha = output.split()[-1]  # Alpha channel

        # At least some pixels should be transparent (alpha < 255)
        alpha_data = list(alpha.getdata())
        transparent_pixels = sum(1 for a in alpha_data if a < 128)
        assert transparent_pixels > 0, "No transparent pixels found — background not removed"

    @pytest.mark.slow
    def test_dimensions_preserved(self, test_image: Path) -> None:
        """Output should have the same dimensions as input."""
        from src.engine.processors.background import remove_background

        original = Image.open(test_image)
        result = remove_background(
            image_path=str(test_image),
            model_id="birefnet-general",
        )

        assert result.image.width == original.width
        assert result.image.height == original.height

    @pytest.mark.slow
    def test_metadata_in_response(self, test_image: Path) -> None:
        """Verify response contains expected metadata fields."""
        from src.engine.processors.background import remove_background

        result = remove_background(
            image_path=str(test_image),
            model_id="birefnet-general",
        )

        assert result.processing_time_ms > 0
        assert result.original_size_bytes > 0
        assert result.model_used == "birefnet-general"
        assert Path(result.image.file_path).exists()

    @pytest.mark.slow
    def test_batch_remove_background(self, test_image: Path, tmp_path: Path) -> None:
        """Verify batch removal across multiple images."""
        from src.engine.processors.background import batch_remove_background

        img2_path = tmp_path / "img2.png"
        img2 = Image.new("RGB", (128, 128), (0, 255, 0))
        img2.save(str(img2_path))

        result = batch_remove_background(
            image_paths=[str(test_image), str(img2_path)],
            model_id="birefnet-general",
        )
        assert result.total == 2
        assert result.succeeded == 2
        assert result.failed == 0
        assert len(result.results) == 2
        assert result.results[0].success is True
        assert result.results[1].success is True
