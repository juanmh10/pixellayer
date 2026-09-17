"""
Image Optimizer
================
Reduces file size through quality adjustment, metadata stripping,
and iterative compression to reach a target file size.

Supports preset optimization levels and target-size-in-KB mode.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image

from src.contracts.schemas import (
    ImageMetadata,
    OptimizationLevel,
    OptimizeImageOutput,
)
from src.utils.exceptions import FileNotFoundError_, ProcessingError
from src.utils.files import (
    calculate_reduction,
    ensure_parent_dir,
    generate_output_path,
    human_readable_size,
    to_safe_relative_path,
)

logger = logging.getLogger(__name__)

# Quality presets for each optimization level
QUALITY_PRESETS: dict[OptimizationLevel, dict] = {
    OptimizationLevel.LOSSLESS: {"quality": 100, "optimize": True, "strip_meta": True},
    OptimizationLevel.LIGHT: {"quality": 85, "optimize": True, "strip_meta": True},
    OptimizationLevel.MEDIUM: {"quality": 70, "optimize": True, "strip_meta": True},
    OptimizationLevel.AGGRESSIVE: {"quality": 45, "optimize": True, "strip_meta": True},
}


def _strip_metadata(image: Image.Image) -> Image.Image:
    """Remove EXIF and other metadata from image by re-creating pixel data."""
    # Use get_flattened_data if available (Pillow 12+), fallback to getdata
    if hasattr(image, "get_flattened_data"):
        data = list(image.get_flattened_data())
    else:
        data = list(image.getdata())
    clean = Image.new(image.mode, image.size)
    clean.putdata(data)
    return clean


def _save_with_quality(
    image: Image.Image,
    output_path: Path,
    quality: int,
    optimize: bool = True,
) -> int:
    """Save image and return file size in bytes.

    Determines format from output_path extension.
    """
    ext = output_path.suffix.lower()

    save_kwargs: dict = {"optimize": optimize}

    if ext in (".jpg", ".jpeg"):
        image_to_save = image.convert("RGB") if image.mode != "RGB" else image
        image_to_save.save(
            str(output_path),
            format="JPEG",
            quality=quality,
            progressive=True,
            **save_kwargs,
        )
    elif ext == ".webp":
        if quality >= 100:
            image.save(str(output_path), format="WEBP", lossless=True, **save_kwargs)
        else:
            image.save(str(output_path), format="WEBP", quality=quality, **save_kwargs)
    elif ext == ".png":
        # PNG is lossless — quality doesn't apply, but we can optimize
        image.save(str(output_path), format="PNG", **save_kwargs)
    else:
        image.save(str(output_path), **save_kwargs)

    return output_path.stat().st_size


def _optimize_to_target_size(
    image: Image.Image,
    output_path: Path,
    target_kb: int,
    min_quality: int = 10,
    max_quality: int = 95,
) -> tuple[int, int]:
    """Binary search for optimal quality to reach target file size.

    Returns:
        Tuple of (final_quality, final_size_bytes).
    """
    target_bytes = target_kb * 1024
    low, high = min_quality, max_quality
    best_quality = low
    best_size = 0

    for _ in range(12):  # Max 12 iterations for binary search
        mid = (low + high) // 2
        size = _save_with_quality(image, output_path, quality=mid)

        if size <= target_bytes:
            best_quality = mid
            best_size = size
            low = mid + 1
        else:
            high = mid - 1

    # Final save with best quality
    if best_size == 0 or best_quality != (low + high) // 2:
        best_size = _save_with_quality(image, output_path, quality=best_quality)

    return best_quality, best_size


def optimize_image(
    image_path: str,
    level: OptimizationLevel = OptimizationLevel.MEDIUM,
    target_size_kb: int | None = None,
    strip_metadata: bool = True,
    output_path: str | None = None,
) -> OptimizeImageOutput:
    """Optimize an image for reduced file size.

    Args:
        image_path: Absolute path to the input image.
        level: Optimization preset (lossless, light, medium, aggressive).
        target_size_kb: Target size in KB. Overrides level if set.
        strip_metadata: Remove EXIF and other metadata.
        output_path: Where to save. Auto-generated if None.

    Returns:
        OptimizeImageOutput with metadata and reduction stats.
    """
    start_time = time.monotonic()

    input_path = Path(image_path)
    if not input_path.exists():
        raise FileNotFoundError_(str(input_path))

    original_size = input_path.stat().st_size

    # Resolve output path
    if output_path:
        out_path = ensure_parent_dir(output_path)
    else:
        out_path = generate_output_path(input_path, suffix="_optimized")

    try:
        image = Image.open(input_path)

        # Strip metadata if requested
        if strip_metadata:
            image = _strip_metadata(image)

        if target_size_kb is not None:
            # Target size mode — binary search
            logger.info(f"Optimizing to target size: {target_size_kb} KB")
            final_quality, output_size = _optimize_to_target_size(image, out_path, target_size_kb)
            used_level = f"target_{target_size_kb}kb"
        else:
            # Preset mode
            preset = QUALITY_PRESETS[level]
            output_size = _save_with_quality(
                image,
                out_path,
                quality=preset["quality"],
                optimize=preset["optimize"],
            )
            used_level = level.value

        # Re-read to get accurate metadata
        output_size = out_path.stat().st_size
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        saved_image = Image.open(out_path)

        result = OptimizeImageOutput(
            success=True,
            image=ImageMetadata(
                file_path=to_safe_relative_path(out_path),
                format=out_path.suffix.lstrip("."),
                width=saved_image.width,
                height=saved_image.height,
                file_size_bytes=output_size,
                file_size_human=human_readable_size(output_size),
            ),
            original_size_bytes=original_size,
            reduction_percent=calculate_reduction(original_size, output_size),
            optimization_level=used_level,
            processing_time_ms=elapsed_ms,
        )

        logger.info(
            f"Optimization ({used_level}): {human_readable_size(original_size)} → "
            f"{human_readable_size(output_size)} ({result.reduction_percent:+.1f}%) "
            f"in {elapsed_ms}ms"
        )

        return result

    except FileNotFoundError_:
        raise
    except Exception as e:
        raise ProcessingError("optimize_image", str(e)) from e
