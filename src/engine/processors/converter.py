"""
Format Converter
=================
Converts between image formats: PNG, WebP (lossy/lossless), JPEG.
Preserves alpha channel when target format supports it.
Strips alpha and warns when converting to JPEG.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image

from src.contracts.schemas import (
    ConvertFormatOutput,
    ImageFormat,
    ImageMetadata,
)
from src.utils.exceptions import FileNotFoundError_, ProcessingError, UnsupportedFormatError
from src.utils.files import (
    calculate_reduction,
    ensure_parent_dir,
    generate_output_path,
    human_readable_size,
    to_safe_relative_path,
)

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
FORMAT_SAVE_MAP = {
    ImageFormat.PNG: ("PNG", ".png"),
    ImageFormat.WEBP: ("WEBP", ".webp"),
    ImageFormat.JPEG: ("JPEG", ".jpeg"),
}


def convert_format(
    image_path: str,
    target_format: ImageFormat,
    quality: int = 90,
    lossless: bool = False,
    output_path: str | None = None,
) -> ConvertFormatOutput:
    """Convert an image to a different format.

    Args:
        image_path: Absolute path to the input image.
        target_format: Target format (PNG, WebP, JPEG).
        quality: Quality for lossy formats (1-100).
        lossless: Use lossless compression (WebP only).
        output_path: Where to save. Auto-generated if None.

    Returns:
        ConvertFormatOutput with metadata and reduction stats.
    """
    start_time = time.monotonic()

    input_path = Path(image_path)
    if not input_path.exists():
        raise FileNotFoundError_(str(input_path))

    if input_path.suffix.lower() not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(input_path.suffix, sorted(SUPPORTED_FORMATS))

    original_size = input_path.stat().st_size
    original_format = input_path.suffix.lstrip(".").lower()

    # Resolve output path
    save_format, ext = FORMAT_SAVE_MAP[target_format]
    if output_path:
        out_path = ensure_parent_dir(output_path)
    else:
        out_path = generate_output_path(input_path, suffix="", extension=ext.lstrip("."))
        # Avoid overwriting input if same extension
        if out_path == input_path:
            out_path = generate_output_path(
                input_path, suffix="_converted", extension=ext.lstrip(".")
            )

    try:
        image = Image.open(input_path)

        # Handle alpha channel
        if target_format == ImageFormat.JPEG and image.mode in ("RGBA", "LA", "PA"):
            logger.warning(
                "JPEG does not support transparency. Compositing alpha onto white background."
            )
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        elif target_format == ImageFormat.JPEG:
            image = image.convert("RGB")

        # Save with format-specific options
        save_kwargs: dict = {}

        if target_format == ImageFormat.PNG:
            save_kwargs["optimize"] = True
        elif target_format == ImageFormat.WEBP:
            save_kwargs["quality"] = quality
            save_kwargs["lossless"] = lossless
        elif target_format == ImageFormat.JPEG:
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
            save_kwargs["progressive"] = True

        image.save(str(out_path), format=save_format, **save_kwargs)

        # Gather output metadata
        output_size = out_path.stat().st_size
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Re-open to get accurate dimensions (some formats may change)
        saved_image = Image.open(out_path)

        result = ConvertFormatOutput(
            success=True,
            image=ImageMetadata(
                file_path=to_safe_relative_path(out_path),
                format=ext.lstrip("."),
                width=saved_image.width,
                height=saved_image.height,
                file_size_bytes=output_size,
                file_size_human=human_readable_size(output_size),
            ),
            original_format=original_format,
            original_size_bytes=original_size,
            reduction_percent=calculate_reduction(original_size, output_size),
            processing_time_ms=elapsed_ms,
        )

        logger.info(
            f"Converted {original_format} → {ext.lstrip('.')}: "
            f"{human_readable_size(original_size)} → {human_readable_size(output_size)} "
            f"({result.reduction_percent:+.1f}%) in {elapsed_ms}ms"
        )

        return result

    except (FileNotFoundError_, UnsupportedFormatError):
        raise
    except Exception as e:
        raise ProcessingError("convert_format", str(e)) from e
