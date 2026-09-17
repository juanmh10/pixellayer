"""
Image Resizer
==============
Resizes images with aspect ratio preservation, multiple resampling
algorithms, and various resize modes (fit, fill, exact, percentage).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image

from src.contracts.schemas import (
    ImageMetadata,
    ResampleFilter,
    ResizeImageOutput,
    ResizeMode,
)
from src.utils.exceptions import FileNotFoundError_, ProcessingError
from src.utils.files import (
    ensure_parent_dir,
    generate_output_path,
    human_readable_size,
    to_safe_relative_path,
)

logger = logging.getLogger(__name__)

# Map enum values to Pillow resampling constants
RESAMPLE_MAP = {
    ResampleFilter.LANCZOS: Image.LANCZOS,
    ResampleFilter.BICUBIC: Image.BICUBIC,
    ResampleFilter.BILINEAR: Image.BILINEAR,
    ResampleFilter.NEAREST: Image.NEAREST,
}


def _calculate_fit_dimensions(
    original_width: int,
    original_height: int,
    target_width: int | None,
    target_height: int | None,
) -> tuple[int, int]:
    """Calculate dimensions that fit within target bounds, preserving aspect ratio."""
    if target_width and target_height:
        # Fit within both constraints
        ratio = min(target_width / original_width, target_height / original_height)
    elif target_width:
        ratio = target_width / original_width
    elif target_height:
        ratio = target_height / original_height
    else:
        ratio = 1.0

    new_width = max(1, round(original_width * ratio))
    new_height = max(1, round(original_height * ratio))
    return new_width, new_height


def _calculate_fill_dimensions(
    original_width: int,
    original_height: int,
    target_width: int,
    target_height: int,
) -> tuple[int, int, tuple[int, int, int, int]]:
    """Calculate dimensions for fill mode (cover + center crop).

    Returns:
        Tuple of (resize_width, resize_height, crop_box).
    """
    ratio = max(target_width / original_width, target_height / original_height)
    resize_width = max(1, round(original_width * ratio))
    resize_height = max(1, round(original_height * ratio))

    # Center crop
    left = (resize_width - target_width) // 2
    top = (resize_height - target_height) // 2
    crop_box = (left, top, left + target_width, top + target_height)

    return resize_width, resize_height, crop_box


def resize_image(
    image_path: str,
    width: int | None = None,
    height: int | None = None,
    scale_percent: float | None = None,
    mode: ResizeMode = ResizeMode.FIT,
    resample: ResampleFilter = ResampleFilter.LANCZOS,
    output_path: str | None = None,
) -> ResizeImageOutput:
    """Resize an image with various modes and filters.

    Args:
        image_path: Absolute path to the input image.
        width: Target width in pixels.
        height: Target height in pixels.
        scale_percent: Scale as percentage (50 = half size). Overrides width/height.
        mode: Resize mode (fit, fill, exact, percentage).
        resample: Resampling filter algorithm.
        output_path: Where to save. Auto-generated if None.

    Returns:
        ResizeImageOutput with metadata and scale ratio.
    """
    start_time = time.monotonic()

    input_path = Path(image_path)
    if not input_path.exists():
        raise FileNotFoundError_(str(input_path))

    # Resolve output path
    if output_path:
        out_path = ensure_parent_dir(output_path)
    else:
        out_path = generate_output_path(input_path, suffix="_resized")

    try:
        image = Image.open(input_path)
        original_width, original_height = image.size
        resample_filter = RESAMPLE_MAP[resample]

        # Calculate target dimensions
        if scale_percent is not None:
            # Percentage mode overrides everything
            factor = scale_percent / 100.0
            new_width = max(1, round(original_width * factor))
            new_height = max(1, round(original_height * factor))
            resized = image.resize((new_width, new_height), resample_filter)

        elif mode == ResizeMode.FIT:
            if not width and not height:
                raise ProcessingError(
                    "resize_image",
                    "At least one of 'width', 'height', or 'scale_percent' must be provided.",
                )
            new_width, new_height = _calculate_fit_dimensions(
                original_width, original_height, width, height
            )
            resized = image.resize((new_width, new_height), resample_filter)

        elif mode == ResizeMode.FILL:
            if not width or not height:
                raise ProcessingError(
                    "resize_image",
                    "Both 'width' and 'height' are required for 'fill' mode.",
                )
            resize_w, resize_h, crop_box = _calculate_fill_dimensions(
                original_width, original_height, width, height
            )
            resized = image.resize((resize_w, resize_h), resample_filter)
            resized = resized.crop(crop_box)
            new_width, new_height = resized.size

        elif mode == ResizeMode.EXACT:
            if not width or not height:
                raise ProcessingError(
                    "resize_image",
                    "Both 'width' and 'height' are required for 'exact' mode.",
                )
            new_width, new_height = width, height
            resized = image.resize((new_width, new_height), resample_filter)

        elif mode == ResizeMode.PERCENTAGE:
            if scale_percent is None:
                raise ProcessingError(
                    "resize_image",
                    "'scale_percent' is required for 'percentage' mode.",
                )
            # Already handled above, but be explicit
            factor = scale_percent / 100.0
            new_width = max(1, round(original_width * factor))
            new_height = max(1, round(original_height * factor))
            resized = image.resize((new_width, new_height), resample_filter)
        else:
            raise ProcessingError("resize_image", f"Unknown resize mode: {mode}")

        # Save in the same format as input
        resized.save(str(out_path))

        # Gather metadata
        output_size = out_path.stat().st_size
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        scale_ratio = round((new_width * new_height) / (original_width * original_height), 4)

        result = ResizeImageOutput(
            success=True,
            image=ImageMetadata(
                file_path=to_safe_relative_path(out_path),
                format=out_path.suffix.lstrip("."),
                width=new_width,
                height=new_height,
                file_size_bytes=output_size,
                file_size_human=human_readable_size(output_size),
            ),
            original_width=original_width,
            original_height=original_height,
            scale_ratio=scale_ratio,
            processing_time_ms=elapsed_ms,
        )

        logger.info(
            f"Resize: {original_width}x{original_height} → {new_width}x{new_height} "
            f"(ratio={scale_ratio}) in {elapsed_ms}ms"
        )

        return result

    except (FileNotFoundError_, ProcessingError):
        raise
    except Exception as e:
        raise ProcessingError("resize_image", str(e)) from e
