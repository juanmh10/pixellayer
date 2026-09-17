"""
MCP Tool Definitions
=====================
All MCP tools registered via FastMCP decorators.
Each tool:
- Accepts file paths (NEVER base64/bytes)
- Validates input via Pydantic contracts
- Delegates to engine processors
- Returns file paths + metadata (NEVER image data)
- Handles errors with structured responses

Tools registered:
1. remove_background  — AI background removal with alpha channel
2. convert_format     — PNG/WebP/JPEG conversion
3. optimize_image     — File size reduction
4. resize_image       — Resize with aspect ratio preservation
5. vectorize_image    — Raster to SVG
6. batch_process      — Chain multiple operations
7. list_models        — List available models (NO loading)
8. get_model_info     — Get model details (NO loading)
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.contracts.schemas import (
    BatchStep,
    ImageFormat,
    OptimizationLevel,
    ResampleFilter,
    ResizeMode,
    SaveImageOutput,
    VectorDetailLevel,
)
from src.engine import pipeline
from src.engine.models.registry import registry
from src.engine.processors import background, converter, cropper, optimizer, resizer, vectorizer
from src.utils.exceptions import ImgCutError
from src.utils.files import (
    copy_file_safe,
    human_readable_size,
    resolve_safe_path,
    to_safe_relative_path,
)

logger = logging.getLogger(__name__)


def register_all_tools(mcp: FastMCP) -> None:
    """Register all PixelLayer tools on the FastMCP server instance."""

    # ========================================================================
    # Tool 1: remove_background
    # ========================================================================
    @mcp.tool()
    def remove_background(
        image_path: str,
        model: str = "birefnet-general",
        output_path: str | None = None,
        output_format: str = "png",
    ) -> dict[str, Any]:
        """Remove background from an image with AI-powered segmentation.

        Produces a clean RGBA image with transparent background (alpha channel).
        No fill, no padding — pure transparent pixels where the background was.

        Args:
            image_path: Path to the input image file (relative to workspace).
            model: Model to use. Options: birefnet-general, birefnet-portrait,
                   birefnet-matting, birefnet-hr, rmbg-2.0, isnet-general.
            output_path: Where to save. Auto-generated if not provided.
            output_format: Output format: 'png' (recommended) or 'webp'.

        Returns:
            Dict with output file path, dimensions, size, and processing stats.
        """
        try:
            fmt = ImageFormat(output_format)
            result = background.remove_background(
                image_path=resolve_safe_path(image_path),
                model_id=model,
                output_path=resolve_safe_path(output_path, is_output=True) if output_path else None,
                output_format=fmt,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool remove_background error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool remove_background unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 2: batch_remove_background (Multi-Image)
    # ========================================================================
    @mcp.tool()
    def batch_remove_background(
        image_paths: list[str],
        model: str = "birefnet-general",
        output_dir: str | None = None,
        output_format: str = "png",
    ) -> dict[str, Any]:
        """Remove background from multiple images in a single batch call.

        Highly efficient: keeps model warm across all images and saves token roundtrips.
        Produces RGBA images with alpha transparency for each input.

        Args:
            image_paths: List of relative image file paths to process.
            model: Segmentation model: birefnet-general, birefnet-portrait,
                   birefnet-matting, birefnet-hr, rmbg-2.0, isnet-general.
            output_dir: Optional directory where output files will be saved.
            output_format: Output format: 'png' (default) or 'webp'.

        Returns:
            Dict with total, succeeded, failed counts, total timing, and per-file results.
        """
        try:
            fmt = ImageFormat(output_format)
            resolved_inputs = [resolve_safe_path(p) for p in image_paths]
            resolved_out_dir = resolve_safe_path(output_dir, is_output=True) if output_dir else None
            result = background.batch_remove_background(
                image_paths=resolved_inputs,
                model_id=model,
                output_dir=resolved_out_dir,
                output_format=fmt,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool batch_remove_background error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool batch_remove_background unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 3: crop_image
    # ========================================================================
    @mcp.tool()
    def crop_image(
        image_path: str,
        x: int | None = None,
        y: int | None = None,
        width: int | None = None,
        height: int | None = None,
        box: list[int] | None = None,
        autocrop: bool = False,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Crop an image geometrically using coordinates or auto-trim empty borders.

        Geometric crop operation. Does NOT remove background via AI (use remove_background for that).
        Supports:
        - autocrop: Auto-detects and trims transparent or solid border margins (ideal after remove_background).
        - x, y, width, height: Crop specific rectangular region.
        - box: [left, top, right, bottom] explicit pixel boundaries.

        Args:
            image_path: Path to the input image file (relative to workspace).
            x: Left coordinate of crop area (pixels).
            y: Top coordinate of crop area (pixels).
            width: Width of crop area (pixels).
            height: Height of crop area (pixels).
            box: Explicit [left, top, right, bottom] box. Overrides x/y/width/height.
            autocrop: If True, crops to content bounding box, trimming empty margins.
            output_path: Where to save. Auto-generated if not provided.

        Returns:
            Dict with output file path, cropped dimensions, crop box applied, and reduction stats.
        """
        try:
            result = cropper.crop_image(
                image_path=resolve_safe_path(image_path),
                x=x,
                y=y,
                width=width,
                height=height,
                box=box,
                autocrop=autocrop,
                output_path=resolve_safe_path(output_path, is_output=True) if output_path else None,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool crop_image error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool crop_image unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 2: convert_format
    # ========================================================================
    @mcp.tool()
    def convert_format(
        image_path: str,
        target_format: str,
        quality: int = 90,
        lossless: bool = False,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Convert an image between formats (PNG, WebP, JPEG).

        Preserves alpha channel when target format supports it.
        WebP supports both lossy and lossless compression with alpha.
        JPEG will composite alpha onto white background.

        Args:
            image_path: Path to the input image file (relative or absolute).
            target_format: Target format: 'png', 'webp', or 'jpeg'.
            quality: Quality for lossy formats (1-100). Default: 90.
            lossless: Use lossless compression (WebP only).
            output_path: Where to save. Auto-generated if not provided.

        Returns:
            Dict with output file path, sizes, and reduction percentage.
        """
        try:
            fmt = ImageFormat(target_format)
            result = converter.convert_format(
                image_path=resolve_safe_path(image_path),
                target_format=fmt,
                quality=quality,
                lossless=lossless,
                output_path=resolve_safe_path(output_path, is_output=True) if output_path else None,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool convert_format error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool convert_format unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 5: optimize_image
    # ========================================================================
    @mcp.tool()
    def optimize_image(
        image_path: str,
        level: str = "medium",
        target_size_kb: int | None = None,
        strip_metadata: bool = True,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Optimize an image to reduce file size.

        Supports preset levels (lossless, light, medium, aggressive)
        or a target file size in KB. Strips EXIF metadata by default.

        Args:
            image_path: Path to the input image file (relative to workspace).
            level: Optimization preset: 'lossless', 'light', 'medium', 'aggressive'.
            target_size_kb: Target file size in KB. Overrides 'level' if set.
            strip_metadata: Remove EXIF and other metadata. Default: True.
            output_path: Where to save. Auto-generated if not provided.

        Returns:
            Dict with output file path, sizes, reduction %, and level used.
        """
        try:
            opt_level = OptimizationLevel(level)
            result = optimizer.optimize_image(
                image_path=resolve_safe_path(image_path),
                level=opt_level,
                target_size_kb=target_size_kb,
                strip_metadata=strip_metadata,
                output_path=resolve_safe_path(output_path, is_output=True) if output_path else None,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool optimize_image error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool optimize_image unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 6: resize_image
    # ========================================================================
    @mcp.tool()
    def resize_image(
        image_path: str,
        width: int | None = None,
        height: int | None = None,
        scale_percent: float | None = None,
        mode: str = "fit",
        resample: str = "lanczos",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Resize an image with aspect ratio preservation.

        Supports multiple modes: fit (contain within bounds), fill (cover + crop),
        exact (may distort), or percentage scaling.

        Args:
            image_path: Path to the input image file (relative to workspace).
            width: Target width in pixels.
            height: Target height in pixels.
            scale_percent: Scale as percentage (50 = half size). Overrides width/height.
            mode: Resize mode: 'fit', 'fill', 'exact', 'percentage'.
            resample: Resampling filter: 'lanczos', 'bicubic', 'bilinear', 'nearest'.
            output_path: Where to save. Auto-generated if not provided.

        Returns:
            Dict with output file path, dimensions, and scale ratio.
        """
        try:
            resize_mode = ResizeMode(mode)
            resample_filter = ResampleFilter(resample)
            result = resizer.resize_image(
                image_path=resolve_safe_path(image_path),
                width=width,
                height=height,
                scale_percent=scale_percent,
                mode=resize_mode,
                resample=resample_filter,
                output_path=resolve_safe_path(output_path, is_output=True) if output_path else None,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool resize_image error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool resize_image unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 7: vectorize_image
    # ========================================================================
    @mcp.tool()
    def vectorize_image(
        image_path: str,
        detail_level: str = "logo",
        color_mode: str = "color",
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Convert a raster image to SVG vector format.

        Uses vtracer for high-quality raster-to-vector conversion.
        Defaults to the 'logo' preset for smooth curves, noise-filtered transparency,
        and compact SVG outputs with zero configuration required.

        Args:
            image_path: Path to the input image file (relative to workspace).
            detail_level: Detail preset: 'logo' (clean, smooth curves for logos/icons - DEFAULT),
                          'low', 'medium', 'high'.
            color_mode: 'color' preserves colors, 'binary' produces B&W SVG.
            output_path: Where to save (relative to workspace). Auto-generated if not provided.

        Returns:
            Dict with SVG file path (relative to workspace), size, and path count.
        """
        try:
            detail = VectorDetailLevel(detail_level)
            result = vectorizer.vectorize_image(
                image_path=resolve_safe_path(image_path),
                detail_level=detail,
                color_mode=color_mode,
                output_path=resolve_safe_path(output_path, is_output=True) if output_path else None,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool vectorize_image error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool vectorize_image unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 8: batch_process
    # ========================================================================
    @mcp.tool()
    def batch_process(
        image_path: str,
        steps: list[dict[str, Any]],
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """Apply multiple image operations in sequence.

        Each step's output becomes the next step's input.
        Intermediate files are cleaned up automatically.

        Args:
            image_path: Path to the input image file (relative to workspace).
            steps: List of step objects with 'operation' and 'params' keys.
                   Operations: remove_background, crop_image, convert_format,
                   optimize_image, resize_image, vectorize_image.
                   Params: same as individual tool parameters (minus image_path).
            output_path: Final output file path. Auto-generated if not provided.

        Returns:
            Dict with final file path, per-step results, and total stats.
        """
        try:
            batch_steps = [BatchStep(**s) for s in steps]
            result = pipeline.run_pipeline(
                image_path=resolve_safe_path(image_path),
                steps=batch_steps,
                output_path=resolve_safe_path(output_path, is_output=True) if output_path else None,
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool batch_process error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool batch_process unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 9: list_models (NO MODEL LOADING)
    # ========================================================================
    @mcp.tool()
    def list_models() -> dict[str, Any]:
        """List all available background removal models.

        Returns model IDs, names, and descriptions WITHOUT loading any model.
        This is a lightweight metadata-only call — no GPU resources are used.

        Returns:
            Dict with list of available models and their capabilities.
        """
        try:
            models = registry.list_models()
            return {
                "models": models,
                "total": len(models),
            }
        except Exception as e:
            logger.error(f"Tool list_models unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 10: get_model_info (NO MODEL LOADING)
    # ========================================================================
    @mcp.tool()
    def get_model_info(model_id: str) -> dict[str, Any]:
        """Get detailed information about a specific model.

        Returns model metadata WITHOUT loading weights or using GPU.
        Use this to check model capabilities before calling remove_background.

        Args:
            model_id: The model identifier (e.g., 'birefnet-general').

        Returns:
            Dict with model name, description, loaded status, and capabilities.
        """
        try:
            info = registry.get_model_info(model_id)
            return {"model": info}
        except KeyError as e:
            logger.error(f"Model not found: {e}")
            raise RuntimeError(f"[MODEL_NOT_FOUND] Model '{model_id}' not found.") from e
        except Exception as e:
            logger.error(f"Tool get_model_info unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e

    # ========================================================================
    # Tool 11: save_image (PATH-ONLY COPY/SAVE)
    # ========================================================================
    @mcp.tool()
    def save_image(source_path: str, target_path: str) -> dict[str, Any]:
        """Copy or save a processed image to a designated target location without binary transfer.

        Adheres strictly to the Path-Only Rule: operates on-disk and preserves tokens.
        Allows agents to relocate outputs to their desired folders safely.

        Args:
            source_path: Source file path (relative to workspace).
            target_path: Target file path or directory (relative to workspace).

        Returns:
            Dict with source_path, saved_path, and file size metadata.
        """
        try:
            saved_dst = copy_file_safe(source_path, target_path)
            size = saved_dst.stat().st_size
            result = SaveImageOutput(
                success=True,
                source_path=to_safe_relative_path(source_path),
                saved_path=to_safe_relative_path(saved_dst),
                file_size_bytes=size,
                file_size_human=human_readable_size(size),
                message="Image copied successfully without binary transfer.",
            )
            return result.model_dump()
        except ImgCutError as e:
            logger.error(f"Tool save_image error [{e.code}]: {e.message}")
            raise RuntimeError(f"[{e.code}] {e.message}") from e
        except Exception as e:
            logger.error(f"Tool save_image unexpected error: {e}")
            raise RuntimeError(f"[UNEXPECTED_ERROR] {e}") from e
