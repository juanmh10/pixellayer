"""
Image Cropping Processor
========================
Crop images geometrically (bounding box / coordinates) or automatically
(autocrop non-transparent or uniform background borders).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image

from src.contracts.schemas import CropImageOutput, ImageMetadata
from src.utils.config import config
from src.utils.exceptions import FileNotFoundError_, ProcessingError, UnsupportedFormatError
from src.utils.files import (
    calculate_reduction,
    ensure_parent_dir,
    generate_output_path,
    human_readable_size,
    to_safe_relative_path,
)

logger = logging.getLogger(__name__)

SUPPORTED_INPUT_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def crop_image(
    image_path: str,
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    box: list[int] | tuple[int, int, int, int] | None = None,
    autocrop: bool = False,
    output_path: str | None = None,
) -> CropImageOutput:
    """Crop an image using coordinates or auto-detect content bounding box.

    Args:
        image_path: Path to the input image file.
        x: Left coordinate for crop box (0-based).
        y: Top coordinate for crop box (0-based).
        width: Width of the cropped region.
        height: Height of the cropped region.
        box: Explicit [left, top, right, bottom] box. Overrides x/y/width/height.
        autocrop: If True, crops to content bounding box (trims transparent/empty borders).
        output_path: Target path for saving result. Auto-generated if None.

    Returns:
        CropImageOutput with file path, dimensions, and metadata.
    """
    start_time = time.monotonic()
    input_path = Path(image_path)

    if not input_path.exists():
        raise FileNotFoundError_(str(input_path))

    if input_path.suffix.lower() not in SUPPORTED_INPUT_FORMATS:
        raise UnsupportedFormatError(
            input_path.suffix,
            sorted(SUPPORTED_INPUT_FORMATS),
        )

    original_size = input_path.stat().st_size

    try:
        image = Image.open(input_path)
        orig_w, orig_h = image.size

        # Security check: pixel flood limit
        if orig_w * orig_h > config.MAX_IMAGE_PIXELS:
            raise ProcessingError(
                "crop_image",
                f"Image too large ({orig_w}x{orig_h}). Maximum: {config.MAX_IMAGE_PIXELS:,} pixels.",
            )

        crop_box: tuple[int, int, int, int]

        if autocrop:
            # 1. Autocrop by trimming empty/transparent margins
            bbox = image.getbbox()
            if bbox is None:
                # Fully transparent image — no content to crop
                crop_box = (0, 0, orig_w, orig_h)
            else:
                crop_box = bbox
        elif box is not None:
            # 2. Explicit box [left, top, right, bottom]
            if len(box) != 4:
                raise ProcessingError(
                    "crop_image",
                    f"box must contain 4 values [left, top, right, bottom], got: {box}",
                )
            left, top, right, bottom = (int(v) for v in box)
            crop_box = (left, top, right, bottom)
        elif x is not None and y is not None and width is not None and height is not None:
            # 3. x, y, width, height coordinates
            left = int(x)
            top = int(y)
            right = left + int(width)
            bottom = top + int(height)
            crop_box = (left, top, right, bottom)
        else:
            raise ProcessingError(
                "crop_image",
                "Must provide either 'autocrop=True', 'box=[left, top, right, bottom]', "
                "or 'x', 'y', 'width', and 'height'.",
            )

        # Validate box bounds
        left, top, right, bottom = crop_box
        if left < 0 or top < 0 or right > orig_w or bottom > orig_h:
            raise ProcessingError(
                "crop_image",
                f"Crop box ({left}, {top}, {right}, {bottom}) exceeds image boundaries ({orig_w}x{orig_h}).",
            )
        if left >= right or top >= bottom:
            raise ProcessingError(
                "crop_image",
                f"Invalid crop dimensions: width={right - left}, height={bottom - top} must be > 0.",
            )

        # Perform crop
        cropped_image = image.crop((left, top, right, bottom))
        cropped_w, cropped_h = cropped_image.size

        # Resolve output path
        if output_path:
            out_p = ensure_parent_dir(output_path)
        else:
            out_p = generate_output_path(input_path, suffix="_cropped")

        # Save preserving transparency if RGBA
        save_format = cropped_image.format or ("PNG" if cropped_image.mode == "RGBA" else "PNG")
        if out_p.suffix.lower() == ".webp":
            save_format = "WEBP"
        elif out_p.suffix.lower() in (".jpg", ".jpeg"):
            save_format = "JPEG"
            if cropped_image.mode == "RGBA":
                cropped_image = cropped_image.convert("RGB")
        elif out_p.suffix.lower() == ".png":
            save_format = "PNG"

        cropped_image.save(str(out_p), format=save_format, optimize=True)

        output_size = out_p.stat().st_size
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        return CropImageOutput(
            success=True,
            image=ImageMetadata(
                file_path=to_safe_relative_path(out_p),
                format=out_p.suffix.lstrip("."),
                width=cropped_w,
                height=cropped_h,
                file_size_bytes=output_size,
                file_size_human=human_readable_size(output_size),
            ),
            original_width=orig_w,
            original_height=orig_h,
            crop_box=list(crop_box),
            processing_time_ms=elapsed_ms,
            reduction_percent=calculate_reduction(original_size, output_size),
        )

    except (FileNotFoundError_, UnsupportedFormatError, ProcessingError):
        raise
    except Exception as e:
        raise ProcessingError("crop_image", str(e)) from e
