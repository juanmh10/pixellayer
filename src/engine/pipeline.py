"""
Pipeline Orchestrator
======================
Chains multiple processing steps sequentially.
Each step's output becomes the next step's input.
Used by the batch_process MCP tool.

Example pipeline: remove_background → resize → convert_format → optimize_image
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.contracts.schemas import (
    BatchProcessOutput,
    BatchStep,
    ImageFormat,
    ImageMetadata,
    OptimizationLevel,
    ResampleFilter,
    ResizeMode,
    VectorDetailLevel,
)
from src.engine.processors import background, converter, cropper, optimizer, resizer, vectorizer
from src.utils.exceptions import ProcessingError
from src.utils.files import (
    calculate_reduction,
    ensure_parent_dir,
    human_readable_size,
    to_safe_relative_path,
)

logger = logging.getLogger(__name__)


def _execute_step(
    image_path: str,
    step: BatchStep,
    step_index: int,
    total_steps: int,
) -> tuple[str, dict]:
    """Execute a single pipeline step.

    Args:
        image_path: Current image file path.
        step: The step definition with operation and params.
        step_index: Current step index (0-based).
        total_steps: Total number of steps.

    Returns:
        Tuple of (output_file_path, step_result_dict).
    """
    logger.info(f"Pipeline step {step_index + 1}/{total_steps}: {step.operation}")

    params = step.params.copy()

    if step.operation == "remove_background":
        result = background.remove_background(
            image_path=image_path,
            model_id=params.get("model", "birefnet-general"),
            output_format=ImageFormat(params.get("output_format", "png")),
        )
        return result.image.file_path, {
            "operation": step.operation,
            "model_used": result.model_used,
            "processing_time_ms": result.processing_time_ms,
        }

    elif step.operation == "crop_image":
        result = cropper.crop_image(
            image_path=image_path,
            x=params.get("x"),
            y=params.get("y"),
            width=params.get("width"),
            height=params.get("height"),
            box=params.get("box"),
            autocrop=params.get("autocrop", False),
        )
        return result.image.file_path, {
            "operation": step.operation,
            "crop_box": result.crop_box,
            "processing_time_ms": result.processing_time_ms,
        }

    elif step.operation == "convert_format":
        result = converter.convert_format(
            image_path=image_path,
            target_format=ImageFormat(params.get("target_format", "webp")),
            quality=params.get("quality", 90),
            lossless=params.get("lossless", False),
        )
        return result.image.file_path, {
            "operation": step.operation,
            "format": result.image.format,
            "reduction_percent": result.reduction_percent,
            "processing_time_ms": result.processing_time_ms,
        }

    elif step.operation == "optimize_image":
        result = optimizer.optimize_image(
            image_path=image_path,
            level=OptimizationLevel(params.get("level", "medium")),
            target_size_kb=params.get("target_size_kb"),
            strip_metadata=params.get("strip_metadata", True),
        )
        return result.image.file_path, {
            "operation": step.operation,
            "optimization_level": result.optimization_level,
            "reduction_percent": result.reduction_percent,
            "processing_time_ms": result.processing_time_ms,
        }

    elif step.operation == "resize_image":
        result = resizer.resize_image(
            image_path=image_path,
            width=params.get("width"),
            height=params.get("height"),
            scale_percent=params.get("scale_percent"),
            mode=ResizeMode(params.get("mode", "fit")),
            resample=ResampleFilter(params.get("resample", "lanczos")),
        )
        return result.image.file_path, {
            "operation": step.operation,
            "new_dimensions": f"{result.image.width}x{result.image.height}",
            "scale_ratio": result.scale_ratio,
            "processing_time_ms": result.processing_time_ms,
        }

    elif step.operation == "vectorize_image":
        result = vectorizer.vectorize_image(
            image_path=image_path,
            detail_level=VectorDetailLevel(params.get("detail_level", "logo")),
            color_mode=params.get("color_mode", "color"),
        )
        return result.svg_path, {
            "operation": step.operation,
            "path_count": result.path_count,
            "svg_size_human": result.svg_size_human,
            "processing_time_ms": result.processing_time_ms,
        }

    else:
        raise ProcessingError(
            "batch_process",
            f"Unknown operation: {step.operation}",
        )


def run_pipeline(
    image_path: str,
    steps: list[BatchStep],
    output_path: str | None = None,
) -> BatchProcessOutput:
    """Execute a pipeline of image processing steps.

    Each step processes the output of the previous step.
    Intermediate files are generated automatically.

    Args:
        image_path: Absolute path to the input image.
        steps: Ordered list of processing steps.
        output_path: Final output path. If None, uses the last step's output.

    Returns:
        BatchProcessOutput with final result and per-step summaries.
    """
    start_time = time.monotonic()
    input_path = Path(image_path)

    if not input_path.exists():
        from src.utils.exceptions import FileNotFoundError_

        raise FileNotFoundError_(str(input_path))

    original_size = input_path.stat().st_size
    current_path = image_path
    step_results: list[dict] = []
    intermediate_files: list[str] = []
    completed = 0

    try:
        for i, step in enumerate(steps):
            output_file, step_result = _execute_step(current_path, step, i, len(steps))

            # Track intermediate files for cleanup (except final output)
            if current_path != image_path:
                intermediate_files.append(current_path)

            current_path = output_file
            step_results.append(step_result)
            completed += 1

        # If custom output_path provided, rename/move the final file
        final_path = Path(current_path)
        if output_path:
            import shutil

            dest = ensure_parent_dir(output_path)
            shutil.move(str(final_path), str(dest))
            final_path = dest

        # Cleanup intermediate files
        for intermediate in intermediate_files:
            try:
                Path(intermediate).unlink(missing_ok=True)
            except Exception:
                pass

        # Gather final metadata
        final_size = final_path.stat().st_size
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        if final_path.suffix.lower() == ".svg":
            width, height = 0, 0
            fmt_str = "svg"
        else:
            from PIL import Image

            with Image.open(final_path) as img:
                width, height = img.width, img.height
            fmt_str = final_path.suffix.lstrip(".")

        result = BatchProcessOutput(
            success=True,
            final_image=ImageMetadata(
                file_path=to_safe_relative_path(final_path),
                format=fmt_str,
                width=width,
                height=height,
                file_size_bytes=final_size,
                file_size_human=human_readable_size(final_size),
            ),
            steps_completed=completed,
            total_steps=len(steps),
            original_size_bytes=original_size,
            total_reduction_percent=calculate_reduction(original_size, final_size),
            total_processing_time_ms=elapsed_ms,
            step_results=step_results,
        )

        logger.info(
            f"Pipeline complete: {completed}/{len(steps)} steps, "
            f"{human_readable_size(original_size)} → {human_readable_size(final_size)} "
            f"({result.total_reduction_percent:+.1f}%) in {elapsed_ms}ms"
        )

        return result

    except Exception as e:
        # Cleanup on error
        for intermediate in intermediate_files:
            try:
                Path(intermediate).unlink(missing_ok=True)
            except Exception:
                pass

        if isinstance(e, (ProcessingError,)):
            raise
        raise ProcessingError("batch_process", str(e)) from e
