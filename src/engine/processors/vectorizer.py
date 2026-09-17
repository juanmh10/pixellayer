"""
Image Vectorizer
=================
Converts raster images to SVG using vtracer.
Supports color modes (color/binary), detail levels, and path simplification.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from src.contracts.schemas import (
    VectorDetailLevel,
    VectorizeImageOutput,
)
from src.utils.exceptions import FileNotFoundError_, ProcessingError
from src.utils.files import (
    ensure_parent_dir,
    generate_output_path,
    human_readable_size,
    to_safe_relative_path,
)

logger = logging.getLogger(__name__)

# vtracer parameters for each detail level
DETAIL_PRESETS: dict[VectorDetailLevel, dict] = {
    VectorDetailLevel.LOGO: {
        "color_precision": 6,
        "layer_difference": 20,
        "corner_threshold": 80,
        "length_threshold": 6.0,
        "splice_threshold": 60,
        "filter_speckle": 10,
        "path_precision": 4,
    },
    VectorDetailLevel.LOW: {
        "color_precision": 4,
        "layer_difference": 32,
        "corner_threshold": 120,
        "length_threshold": 8.0,
        "splice_threshold": 90,
        "filter_speckle": 8,
        "path_precision": 3,
    },
    VectorDetailLevel.MEDIUM: {
        "color_precision": 6,
        "layer_difference": 16,
        "corner_threshold": 60,
        "length_threshold": 4.0,
        "splice_threshold": 45,
        "filter_speckle": 4,
        "path_precision": 5,
    },
    VectorDetailLevel.HIGH: {
        "color_precision": 8,
        "layer_difference": 8,
        "corner_threshold": 30,
        "length_threshold": 2.0,
        "splice_threshold": 22,
        "filter_speckle": 2,
        "path_precision": 8,
    },
}


def _count_svg_paths(svg_content: str) -> int:
    """Count the number of <path> elements in SVG content."""
    return svg_content.count("<path")


def vectorize_image(
    image_path: str,
    detail_level: VectorDetailLevel = VectorDetailLevel.LOGO,
    color_mode: str = "color",
    output_path: str | None = None,
) -> VectorizeImageOutput:
    """Convert a raster image to SVG using vtracer.

    Args:
        image_path: Path to the input image file (relative or absolute).
        detail_level: Detail level preset (logo, low, medium, high).
        color_mode: 'color' preserves colors, 'binary' produces B&W SVG.
        output_path: Where to save. Auto-generated if None.

    Returns:
        VectorizeImageOutput with SVG path and metadata.
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
        out_path = generate_output_path(input_path, suffix="_vector", extension="svg")

    try:
        # Lazy import vtracer & PIL
        import tempfile

        import vtracer
        from PIL import Image

        preset = DETAIL_PRESETS[detail_level]

        # For images with alpha channel, clean threshold transparent noise to prevent halo paths
        temp_input_file: tempfile.NamedTemporaryFile | None = None
        source_image_to_convert = str(input_path)

        try:
            with Image.open(input_path) as img:
                if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
                    rgba_img = img.convert("RGBA")
                    r, g, b, a = rgba_img.split()
                    # Hard threshold alpha anti-aliasing noise: values <= 50 become 0
                    a_clean = a.point(lambda p: 255 if p > 50 else 0)
                    cleaned_img = Image.merge("RGBA", (r, g, b, a_clean))

                    temp_input_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    cleaned_img.save(temp_input_file.name, format="PNG")
                    source_image_to_convert = temp_input_file.name
        except Exception as e:
            logger.debug(f"Alpha pre-filtering skipped: {e}")

        # vtracer.convert_image_to_svg_py handles the conversion
        try:
            vtracer.convert_image_to_svg_py(
                source_image_to_convert,
                str(out_path),
                colormode=color_mode,
                hierarchical="stacked",
                mode="spline",
                filter_speckle=preset["filter_speckle"],
                color_precision=preset["color_precision"],
                layer_difference=preset["layer_difference"],
                corner_threshold=preset["corner_threshold"],
                length_threshold=preset["length_threshold"],
                splice_threshold=preset["splice_threshold"],
                path_precision=preset["path_precision"],
            )
        finally:
            if temp_input_file:
                try:
                    Path(temp_input_file.name).unlink(missing_ok=True)
                except Exception:
                    pass

        # Read SVG to count paths
        svg_content = out_path.read_text(encoding="utf-8")
        path_count = _count_svg_paths(svg_content)

        svg_size = out_path.stat().st_size
        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        result = VectorizeImageOutput(
            success=True,
            svg_path=to_safe_relative_path(out_path),
            svg_size_bytes=svg_size,
            svg_size_human=human_readable_size(svg_size),
            original_size_bytes=original_size,
            path_count=path_count,
            processing_time_ms=elapsed_ms,
        )

        logger.info(
            f"Vectorized: {human_readable_size(original_size)} → "
            f"{human_readable_size(svg_size)} SVG "
            f"({path_count} paths, {detail_level.value} detail) in {elapsed_ms}ms"
        )

        return result

    except FileNotFoundError_:
        raise
    except ImportError:
        raise ProcessingError(
            "vectorize_image",
            "vtracer is not installed. Install with: pip install vtracer",
        )
    except Exception as e:
        raise ProcessingError("vectorize_image", str(e)) from e
