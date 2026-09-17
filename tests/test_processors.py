"""
Processor Unit Tests
=====================
Tests for format converter, optimizer, resizer, and vectorizer processors.
Uses small fixture images generated on-the-fly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from src.contracts.schemas import (
    ImageFormat,
    OptimizationLevel,
    ResampleFilter,
    ResizeMode,
    VectorDetailLevel,
)
from src.engine.processors import converter, cropper, optimizer, resizer, vectorizer
from src.utils.exceptions import FileNotFoundError_, ProcessingError


@pytest.fixture
def sample_rgb_image(tmp_path: Path) -> Path:
    """Create a small RGB test image."""
    img = Image.new("RGB", (200, 150), color=(255, 100, 50))
    path = tmp_path / "sample.png"
    img.save(str(path))
    return path


@pytest.fixture
def sample_rgba_image(tmp_path: Path) -> Path:
    """Create a small RGBA test image with transparency."""
    img = Image.new("RGBA", (200, 150), color=(255, 100, 50, 128))
    path = tmp_path / "sample_rgba.png"
    img.save(str(path))
    return path


@pytest.fixture
def sample_large_image(tmp_path: Path) -> Path:
    """Create a larger test image for optimization tests."""
    img = Image.new("RGB", (1000, 800), color=(100, 150, 200))
    # Add some variation for realistic compression
    pixels = img.load()
    for x in range(0, 1000, 10):
        for y in range(0, 800, 10):
            pixels[x, y] = ((x * 7) % 256, (y * 3) % 256, ((x + y) * 5) % 256)
    path = tmp_path / "large_sample.png"
    img.save(str(path))
    return path


class TestConverter:
    """Test format conversion processor."""

    def test_png_to_webp(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "output.webp"
        result = converter.convert_format(
            image_path=str(sample_rgb_image),
            target_format=ImageFormat.WEBP,
            quality=90,
            output_path=str(output),
        )
        assert result.success is True
        assert output.exists()
        assert result.image.format == "webp"

    def test_png_to_jpeg(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "output.jpeg"
        result = converter.convert_format(
            image_path=str(sample_rgb_image),
            target_format=ImageFormat.JPEG,
            quality=85,
            output_path=str(output),
        )
        assert result.success is True
        assert output.exists()

    def test_rgba_to_jpeg_strips_alpha(self, sample_rgba_image: Path, tmp_path: Path) -> None:
        """JPEG doesn't support alpha — should composite on white."""
        output = tmp_path / "output.jpeg"
        result = converter.convert_format(
            image_path=str(sample_rgba_image),
            target_format=ImageFormat.JPEG,
            output_path=str(output),
        )
        assert result.success is True
        # Verify output is RGB (no alpha)
        img = Image.open(output)
        assert img.mode == "RGB"

    def test_webp_lossless(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "output.webp"
        result = converter.convert_format(
            image_path=str(sample_rgb_image),
            target_format=ImageFormat.WEBP,
            lossless=True,
            output_path=str(output),
        )
        assert result.success is True

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError_):
            converter.convert_format(
                image_path="/nonexistent/image.png",
                target_format=ImageFormat.WEBP,
            )

    def test_auto_output_path(self, sample_rgb_image: Path) -> None:
        result = converter.convert_format(
            image_path=str(sample_rgb_image),
            target_format=ImageFormat.WEBP,
        )
        assert result.success is True
        assert Path(result.image.file_path).exists()


class TestOptimizer:
    """Test image optimization processor."""

    def test_medium_optimization(self, sample_large_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "optimized.png"
        result = optimizer.optimize_image(
            image_path=str(sample_large_image),
            level=OptimizationLevel.MEDIUM,
            output_path=str(output),
        )
        assert result.success is True
        assert output.exists()

    def test_strip_metadata(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "stripped.png"
        result = optimizer.optimize_image(
            image_path=str(sample_rgb_image),
            level=OptimizationLevel.LOSSLESS,
            strip_metadata=True,
            output_path=str(output),
        )
        assert result.success is True

    def test_target_size_kb(self, sample_large_image: Path, tmp_path: Path) -> None:
        """Test binary search optimization to target size."""
        # First convert to JPEG for lossy optimization
        jpeg_path = tmp_path / "large.jpeg"
        img = Image.open(sample_large_image)
        img.save(str(jpeg_path), format="JPEG", quality=95)

        output = tmp_path / "targeted.jpeg"
        result = optimizer.optimize_image(
            image_path=str(jpeg_path),
            target_size_kb=50,
            output_path=str(output),
        )
        assert result.success is True
        # Should be reasonably close to target
        assert result.image.file_size_bytes <= 60 * 1024  # Allow some margin

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError_):
            optimizer.optimize_image(image_path="/nonexistent/image.png")


class TestResizer:
    """Test image resize processor."""

    def test_fit_mode(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "resized.png"
        result = resizer.resize_image(
            image_path=str(sample_rgb_image),
            width=100,
            height=100,
            mode=ResizeMode.FIT,
            output_path=str(output),
        )
        assert result.success is True
        # Should fit within 100x100, preserving aspect ratio (200:150 = 4:3)
        assert result.image.width <= 100
        assert result.image.height <= 100

    def test_exact_mode(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "exact.png"
        result = resizer.resize_image(
            image_path=str(sample_rgb_image),
            width=300,
            height=300,
            mode=ResizeMode.EXACT,
            output_path=str(output),
        )
        assert result.success is True
        assert result.image.width == 300
        assert result.image.height == 300

    def test_percentage_scale(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "scaled.png"
        result = resizer.resize_image(
            image_path=str(sample_rgb_image),
            scale_percent=50.0,
            output_path=str(output),
        )
        assert result.success is True
        assert result.image.width == 100  # 200 * 0.5
        assert result.image.height == 75  # 150 * 0.5

    def test_width_only(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "width_only.png"
        result = resizer.resize_image(
            image_path=str(sample_rgb_image),
            width=100,
            output_path=str(output),
        )
        assert result.success is True
        assert result.image.width == 100
        # Height should be proportional: 150 * (100/200) = 75
        assert result.image.height == 75

    def test_fill_mode(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "filled.png"
        result = resizer.resize_image(
            image_path=str(sample_rgb_image),
            width=100,
            height=100,
            mode=ResizeMode.FILL,
            output_path=str(output),
        )
        assert result.success is True
        assert result.image.width == 100
        assert result.image.height == 100

    def test_lanczos_filter(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "lanczos.png"
        result = resizer.resize_image(
            image_path=str(sample_rgb_image),
            width=100,
            resample=ResampleFilter.LANCZOS,
            output_path=str(output),
        )
        assert result.success is True

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError_):
            resizer.resize_image(image_path="/nonexistent/image.png", width=100)


class TestVectorizer:
    """Test image vectorization processor."""

    def test_basic_vectorization(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "vector.svg"
        result = vectorizer.vectorize_image(
            image_path=str(sample_rgb_image),
            detail_level=VectorDetailLevel.LOW,
            output_path=str(output),
        )
        assert result.success is True
        assert output.exists()
        assert output.suffix == ".svg"
        assert result.path_count > 0

    def test_binary_mode(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "binary.svg"
        result = vectorizer.vectorize_image(
            image_path=str(sample_rgb_image),
            detail_level=VectorDetailLevel.MEDIUM,
            color_mode="binary",
            output_path=str(output),
        )
        assert result.success is True

    def test_high_detail(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output_low = tmp_path / "low.svg"
        output_high = tmp_path / "high.svg"

        result_low = vectorizer.vectorize_image(
            image_path=str(sample_rgb_image),
            detail_level=VectorDetailLevel.LOW,
            output_path=str(output_low),
        )
        result_high = vectorizer.vectorize_image(
            image_path=str(sample_rgb_image),
            detail_level=VectorDetailLevel.HIGH,
            output_path=str(output_high),
        )

        # Higher detail should produce more paths
        assert result_high.path_count >= result_low.path_count

    def test_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError_):
            vectorizer.vectorize_image(image_path="/nonexistent/image.png")


class TestCropper:
    """Test image cropping processor."""

    def test_crop_coordinates(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "cropped.png"
        result = cropper.crop_image(
            image_path=str(sample_rgb_image),
            x=10,
            y=20,
            width=50,
            height=40,
            output_path=str(output),
        )
        assert result.success is True
        assert output.exists()
        assert result.image.width == 50
        assert result.image.height == 40
        assert result.crop_box == [10, 20, 60, 60]

    def test_crop_box(self, sample_rgb_image: Path, tmp_path: Path) -> None:
        output = tmp_path / "cropped_box.png"
        result = cropper.crop_image(
            image_path=str(sample_rgb_image),
            box=[5, 5, 105, 55],
            output_path=str(output),
        )
        assert result.success is True
        assert result.image.width == 100
        assert result.image.height == 50
        assert result.crop_box == [5, 5, 105, 55]

    def test_autocrop_rgba(self, tmp_path: Path) -> None:
        # Create an image with transparent borders: 100x100 transparent canvas with a 40x40 centered square
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        square = Image.new("RGBA", (40, 40), (255, 0, 0, 255))
        img.paste(square, (30, 30))
        input_path = tmp_path / "autocrop_input.png"
        img.save(str(input_path))

        output_path = tmp_path / "autocrop_out.png"
        result = cropper.crop_image(
            image_path=str(input_path),
            autocrop=True,
            output_path=str(output_path),
        )
        assert result.success is True
        assert result.image.width == 40
        assert result.image.height == 40
        assert result.crop_box == [30, 30, 70, 70]

    def test_crop_exceeds_boundaries(self, sample_rgb_image: Path) -> None:
        with pytest.raises(ProcessingError):
            cropper.crop_image(
                image_path=str(sample_rgb_image),
                x=0,
                y=0,
                width=500,  # Exceeds sample image width (200)
                height=100,
            )

    def test_crop_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError_):
            cropper.crop_image(image_path="/nonexistent/image.png", x=0, y=0, width=10, height=10)
