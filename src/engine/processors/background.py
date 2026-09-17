"""
Background Removal Processor
==============================
Orchestrates background removal using the model registry.
Handles image loading from disk, model selection, inference,
and saving RGBA output with clean alpha channel.

This is the bridge between MCP tools and model wrappers.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image

from src.contracts.schemas import (
    BatchRemoveBackgroundItem,
    BatchRemoveBackgroundOutput,
    ImageFormat,
    ImageMetadata,
    RemoveBackgroundOutput,
)
from src.engine.models.registry import registry
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
FORMAT_EXTENSION_MAP = {
    ImageFormat.PNG: ".png",
    ImageFormat.WEBP: ".webp",
    ImageFormat.JPEG: ".jpeg",
}


def remove_background(
    image_path: str,
    model_id: str = "birefnet-general",
    output_path: str | None = None,
    output_format: ImageFormat = ImageFormat.PNG,
) -> RemoveBackgroundOutput:
    """Remove background from an image file.

    Args:
        image_path: Absolute path to the input image.
        model_id: Model to use for segmentation.
        output_path: Where to save the result. Auto-generated if None.
        output_format: Output format (PNG recommended for lossless alpha).

    Returns:
        RemoveBackgroundOutput with file path, metadata, and timing.

    Raises:
        FileNotFoundError_: Input file does not exist.
        UnsupportedFormatError: Input format not supported.
        ProcessingError: Inference or save failed.
    """
    start_time = time.monotonic()

    # Validate input file
    input_path = Path(image_path)
    if not input_path.exists():
        raise FileNotFoundError_(str(input_path))

    if input_path.suffix.lower() not in SUPPORTED_INPUT_FORMATS:
        raise UnsupportedFormatError(
            input_path.suffix,
            sorted(SUPPORTED_INPUT_FORMATS),
        )

    original_size = input_path.stat().st_size

    # Resolve output path
    ext = FORMAT_EXTENSION_MAP.get(output_format, ".png")
    if output_path:
        out_path = ensure_parent_dir(output_path)
    else:
        out_path = generate_output_path(input_path, suffix="_nobg", extension=ext.lstrip("."))

    try:
        # Load image from disk
        logger.info(f"Loading image: {input_path}")
        image = Image.open(input_path)

        # Check image size limit
        total_pixels = image.width * image.height
        if total_pixels > config.MAX_IMAGE_PIXELS:
            raise ProcessingError(
                "remove_background",
                f"Image too large ({image.width}x{image.height} = {total_pixels:,} pixels). "
                f"Maximum: {config.MAX_IMAGE_PIXELS:,} pixels.",
            )

        # Get model from registry and run inference
        model = registry.get(model_id)
        logger.info(f"Running inference with model '{model_id}'...")
        rgba_image = model.predict(image)

        # Save output
        logger.info(f"Saving result to: {out_path}")

        if output_format == ImageFormat.PNG:
            rgba_image.save(str(out_path), format="PNG", optimize=True)
        elif output_format == ImageFormat.WEBP:
            # WebP supports alpha channel
            rgba_image.save(str(out_path), format="WEBP", quality=90, lossless=False)
        elif output_format == ImageFormat.JPEG:
            # JPEG doesn't support alpha — save as PNG instead and warn
            logger.warning("JPEG does not support alpha channel. Saving as PNG instead.")
            out_path = generate_output_path(input_path, suffix="_nobg", extension="png")
            rgba_image.save(str(out_path), format="PNG", optimize=True)

        # Gather output metadata
        output_size = out_path.stat().st_size
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        result = RemoveBackgroundOutput(
            success=True,
            image=ImageMetadata(
                file_path=to_safe_relative_path(out_path),
                format=out_path.suffix.lstrip("."),
                width=rgba_image.width,
                height=rgba_image.height,
                file_size_bytes=output_size,
                file_size_human=human_readable_size(output_size),
            ),
            model_used=model_id,
            processing_time_ms=elapsed_ms,
            original_size_bytes=original_size,
            reduction_percent=calculate_reduction(original_size, output_size),
        )

        logger.info(
            f"Background removal complete: {human_readable_size(original_size)} → "
            f"{human_readable_size(output_size)} ({result.reduction_percent:+.1f}%) "
            f"in {elapsed_ms}ms"
        )

        return result

    except KeyError as e:
        raise e
    except (FileNotFoundError_, UnsupportedFormatError, ProcessingError):
        raise
    except Exception as e:
        raise ProcessingError("remove_background", str(e)) from e


def batch_remove_background(
    image_paths: list[str],
    model_id: str = "birefnet-general",
    output_dir: str | None = None,
    output_format: ImageFormat = ImageFormat.PNG,
) -> BatchRemoveBackgroundOutput:
    """Process multiple images for background removal in a single batch.

    Args:
        image_paths: List of file paths to process.
        model_id: Model to use for segmentation.
        output_dir: Optional directory to place output files.
        output_format: Output format (PNG recommended for alpha transparency).

    Returns:
        BatchRemoveBackgroundOutput with consolidated results per image.
    """
    total_start = time.monotonic()
    results: list[BatchRemoveBackgroundItem] = []
    succeeded = 0
    failed = 0

    # Ensure model is warm before processing batch
    model = registry.get(model_id)
    model.ensure_loaded()

    for path_str in image_paths:
        item_start = time.monotonic()
        try:
            input_p = Path(path_str)
            out_target: str | None = None
            if output_dir:
                ext = FORMAT_EXTENSION_MAP.get(output_format, ".png")
                out_target = str(Path(output_dir) / f"{input_p.stem}_nobg{ext}")

            single_result = remove_background(
                image_path=path_str,
                model_id=model_id,
                output_path=out_target,
                output_format=output_format,
            )
            item_elapsed = int((time.monotonic() - item_start) * 1000)
            results.append(
                BatchRemoveBackgroundItem(
                    input_path=to_safe_relative_path(path_str),
                    output_path=single_result.image.file_path,
                    success=True,
                    width=single_result.image.width,
                    height=single_result.image.height,
                    file_size_bytes=single_result.image.file_size_bytes,
                    file_size_human=single_result.image.file_size_human,
                    processing_time_ms=item_elapsed,
                )
            )
            succeeded += 1
        except Exception as e:
            item_elapsed = int((time.monotonic() - item_start) * 1000)
            results.append(
                BatchRemoveBackgroundItem(
                    input_path=to_safe_relative_path(path_str),
                    success=False,
                    error=str(e),
                    processing_time_ms=item_elapsed,
                )
            )
            failed += 1

    total_elapsed = int((time.monotonic() - total_start) * 1000)
    return BatchRemoveBackgroundOutput(
        success=failed == 0,
        total=len(image_paths),
        succeeded=succeeded,
        failed=failed,
        total_processing_time_ms=total_elapsed,
        results=results,
    )
