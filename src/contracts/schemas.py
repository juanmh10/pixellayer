"""
MCP Tool Contracts
===================
Pydantic v2 models for all MCP tool inputs and outputs.
All image data is referenced by file path — NEVER as base64 or bytes.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ============================================================================
# Enums
# ============================================================================


class ImageFormat(str, Enum):
    """Supported output image formats."""

    PNG = "png"
    WEBP = "webp"
    JPEG = "jpeg"


class ResizeMode(str, Enum):
    """How to interpret resize dimensions."""

    FIT = "fit"  # Fit within max dimensions, preserve aspect ratio
    FILL = "fill"  # Fill dimensions, crop to fit
    EXACT = "exact"  # Exact dimensions (may distort)
    PERCENTAGE = "percentage"  # Scale by percentage


class ResampleFilter(str, Enum):
    """Resampling filter for resize operations."""

    LANCZOS = "lanczos"
    BICUBIC = "bicubic"
    BILINEAR = "bilinear"
    NEAREST = "nearest"


class OptimizationLevel(str, Enum):
    """Preset optimization levels."""

    LOSSLESS = "lossless"  # No quality loss, strip metadata only
    LIGHT = "light"  # Minimal quality loss, good compression
    MEDIUM = "medium"  # Balanced quality/size
    AGGRESSIVE = "aggressive"  # Maximum compression, noticeable quality loss


class VectorDetailLevel(str, Enum):
    """Detail level for raster-to-SVG vectorization."""

    LOW = "low"  # Simplified paths, smaller SVG
    MEDIUM = "medium"  # Balanced detail
    HIGH = "high"  # Maximum detail for complex photographic raster
    LOGO = "logo"  # Optimized for logos, icons & flat design (clean curves, noise-filtered)


# ============================================================================
# Common
# ============================================================================


class ImageMetadata(BaseModel):
    """Metadata about a processed image. Returned in all tool responses."""

    file_path: str = Field(description="Path to the output image file")
    format: str = Field(description="Output format (png, webp, jpeg, svg)")
    width: int = Field(description="Image width in pixels")
    height: int = Field(description="Image height in pixels")
    file_size_bytes: int = Field(description="File size in bytes")
    file_size_human: str = Field(description="Human-readable file size (e.g., '1.2 MB')")


# ============================================================================
# remove_background
# ============================================================================


class RemoveBackgroundInput(BaseModel):
    """Input for the remove_background tool."""

    image_path: str = Field(
        description="Path to the input image file (relative to workspace or absolute)"
    )
    model: str = Field(
        default="birefnet-general",
        description=(
            "Model to use for background removal. Options: "
            "birefnet-general, birefnet-portrait, birefnet-matting, "
            "birefnet-hr, rmbg-2.0, isnet-general"
        ),
    )
    output_path: str | None = Field(
        default=None,
        description=(
            "Path for the output file (relative to workspace or absolute). "
            "If not provided, saves next to input with '_nobg' suffix."
        ),
    )
    output_format: ImageFormat = Field(
        default=ImageFormat.PNG,
        description="Output format. PNG recommended for lossless alpha.",
    )


class RemoveBackgroundOutput(BaseModel):
    """Output from the remove_background tool."""

    success: bool
    image: ImageMetadata
    model_used: str = Field(description="Model ID that was used")
    processing_time_ms: int = Field(description="Processing time in milliseconds")
    original_size_bytes: int = Field(description="Original file size")
    reduction_percent: float = Field(description="Size change as percentage")


# ============================================================================
# convert_format
# ============================================================================


class ConvertFormatInput(BaseModel):
    """Input for the convert_format tool."""

    image_path: str = Field(
        description="Path to the input image file (relative to workspace or allowed path)"
    )
    target_format: ImageFormat = Field(description="Target format to convert to")
    quality: int = Field(
        default=90,
        ge=1,
        le=100,
        description="Quality for lossy formats (WebP, JPEG). 1-100.",
    )
    lossless: bool = Field(
        default=False,
        description="Use lossless compression (WebP only).",
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (relative or absolute). Auto-generated if not provided.",
    )


class ConvertFormatOutput(BaseModel):
    """Output from the convert_format tool."""

    success: bool
    image: ImageMetadata
    original_format: str
    original_size_bytes: int
    reduction_percent: float
    processing_time_ms: int


# ============================================================================
# optimize_image
# ============================================================================


class OptimizeImageInput(BaseModel):
    """Input for the optimize_image tool."""

    image_path: str = Field(
        description="Path to the input image file (relative to workspace or allowed path)"
    )
    level: OptimizationLevel = Field(
        default=OptimizationLevel.MEDIUM,
        description="Optimization preset level.",
    )
    target_size_kb: int | None = Field(
        default=None,
        description=(
            "Target file size in KB. Will iteratively adjust quality. Overrides 'level' if set."
        ),
    )
    strip_metadata: bool = Field(
        default=True,
        description="Remove EXIF and other metadata.",
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (relative to workspace). Auto-generated if not provided.",
    )


class OptimizeImageOutput(BaseModel):
    """Output from the optimize_image tool."""

    success: bool
    image: ImageMetadata
    original_size_bytes: int
    reduction_percent: float
    optimization_level: str
    processing_time_ms: int


# ============================================================================
# resize_image
# ============================================================================


class ResizeImageInput(BaseModel):
    """Input for the resize_image tool."""

    image_path: str = Field(
        description="Path to the input image file (relative to workspace or allowed path)"
    )
    width: int | None = Field(default=None, gt=0, description="Target width in pixels")
    height: int | None = Field(default=None, gt=0, description="Target height in pixels")
    scale_percent: float | None = Field(
        default=None,
        description="Scale factor as percentage (e.g., 50 for half size). Overrides width/height.",
    )
    mode: ResizeMode = Field(
        default=ResizeMode.FIT,
        description="Resize mode. 'fit' preserves aspect ratio within bounds.",
    )
    resample: ResampleFilter = Field(
        default=ResampleFilter.LANCZOS,
        description="Resampling filter algorithm.",
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (relative to workspace).",
    )


class ResizeImageOutput(BaseModel):
    """Output from the resize_image tool."""

    success: bool
    image: ImageMetadata
    original_width: int
    original_height: int
    scale_ratio: float = Field(description="Actual scale ratio applied")
    processing_time_ms: int


# ============================================================================
# crop_image
# ============================================================================


class CropImageInput(BaseModel):
    """Input for the crop_image tool."""

    image_path: str = Field(
        description="Path to the input image file (relative to workspace or allowed path)"
    )
    x: int | None = Field(default=None, ge=0, description="Left coordinate for crop box")
    y: int | None = Field(default=None, ge=0, description="Top coordinate for crop box")
    width: int | None = Field(default=None, gt=0, description="Width of cropped region in pixels")
    height: int | None = Field(default=None, gt=0, description="Height of cropped region in pixels")
    box: list[int] | None = Field(
        default=None,
        description="Explicit [left, top, right, bottom] box. Overrides x/y/width/height.",
    )
    autocrop: bool = Field(
        default=False,
        description="Auto-detect content bounding box (trims transparent or uniform borders).",
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (relative to workspace).",
    )


class CropImageOutput(BaseModel):
    """Output from the crop_image tool."""

    success: bool
    image: ImageMetadata
    original_width: int
    original_height: int
    crop_box: list[int] = Field(description="Actual [left, top, right, bottom] box applied")
    processing_time_ms: int
    reduction_percent: float


# ============================================================================
# vectorize_image
# ============================================================================


class VectorizeImageInput(BaseModel):
    """Input for the vectorize_image tool."""

    image_path: str = Field(
        description="Path to the input image file (relative to workspace or allowed path)"
    )
    detail_level: VectorDetailLevel = Field(
        default=VectorDetailLevel.LOGO,
        description=(
            "Detail level for vectorization: 'logo' (clean curves, noise-filtered, recommended for logos/icons - DEFAULT), "
            "'medium' (balanced), 'high' (maximum paths for complex raster), or 'low' (minimal paths)."
        ),
    )
    color_mode: Literal["color", "binary"] = Field(
        default="color",
        description="'color' preserves colors, 'binary' produces B&W SVG.",
    )
    output_path: str | None = Field(
        default=None,
        description="Output SVG file path (relative to workspace).",
    )


class VectorizeImageOutput(BaseModel):
    """Output from the vectorize_image tool."""

    success: bool
    svg_path: str = Field(description="Path to the output SVG file")
    svg_size_bytes: int
    svg_size_human: str
    original_size_bytes: int
    path_count: int = Field(description="Number of SVG paths generated")
    processing_time_ms: int


# ============================================================================
# batch_remove_background (Multi-Image)
# ============================================================================


class BatchRemoveBackgroundInput(BaseModel):
    """Input for batch background removal across multiple images."""

    image_paths: list[str] = Field(
        description="List of relative image file paths to process.",
        min_length=1,
    )
    model_id: str = Field(
        default="birefnet-general",
        description="Model to use for segmentation.",
    )
    output_dir: str | None = Field(
        default=None,
        description="Target directory for output images (relative to workspace).",
    )


class BatchRemoveBackgroundItem(BaseModel):
    """Result for a single image in a batch removal operation."""

    input_path: str
    output_path: str | None = None
    success: bool
    error: str | None = None
    width: int | None = None
    height: int | None = None
    file_size_bytes: int | None = None
    file_size_human: str | None = None
    processing_time_ms: int | None = None


class BatchRemoveBackgroundOutput(BaseModel):
    """Output from batch background removal."""

    success: bool
    total: int
    succeeded: int
    failed: int
    total_processing_time_ms: int
    results: list[BatchRemoveBackgroundItem]


# ============================================================================
# batch_process (Pipeline)
# ============================================================================


class RemoveBackgroundStepParams(BaseModel):
    model: str = "birefnet-general"
    output_format: ImageFormat = ImageFormat.PNG


class RemoveBackgroundStep(BaseModel):
    operation: Literal["remove_background"] = "remove_background"
    params: RemoveBackgroundStepParams = Field(default_factory=RemoveBackgroundStepParams)


class CropStepParams(BaseModel):
    x: int | None = None
    y: int | None = None
    width: int | None = None
    height: int | None = None
    box: list[int] | None = None
    autocrop: bool = False


class CropStep(BaseModel):
    operation: Literal["crop_image"] = "crop_image"
    params: CropStepParams = Field(default_factory=CropStepParams)


class ConvertStepParams(BaseModel):
    target_format: ImageFormat = ImageFormat.WEBP
    quality: int = 90
    lossless: bool = False


class ConvertStep(BaseModel):
    operation: Literal["convert_format"] = "convert_format"
    params: ConvertStepParams = Field(default_factory=ConvertStepParams)


class OptimizeStepParams(BaseModel):
    level: OptimizationLevel = OptimizationLevel.MEDIUM
    target_size_kb: int | None = None


class OptimizeStep(BaseModel):
    operation: Literal["optimize_image"] = "optimize_image"
    params: OptimizeStepParams = Field(default_factory=OptimizeStepParams)


class ResizeStepParams(BaseModel):
    width: int | None = None
    height: int | None = None
    scale_percent: float | None = None
    mode: ResizeMode = ResizeMode.FIT
    resample: ResampleFilter = ResampleFilter.LANCZOS


class ResizeStep(BaseModel):
    operation: Literal["resize_image"] = "resize_image"
    params: ResizeStepParams = Field(default_factory=ResizeStepParams)


class VectorizeStepParams(BaseModel):
    detail_level: VectorDetailLevel = VectorDetailLevel.LOGO
    color_mode: Literal["color", "binary"] = "color"


class VectorizeStep(BaseModel):
    operation: Literal["vectorize_image"] = "vectorize_image"
    params: VectorizeStepParams = Field(default_factory=VectorizeStepParams)


BatchStepUnion = Annotated[
    RemoveBackgroundStep | CropStep | ConvertStep | OptimizeStep | ResizeStep | VectorizeStep,
    Field(discriminator="operation"),
]


class BatchStep(BaseModel):
    """A single step in a batch processing pipeline."""

    operation: Literal[
        "remove_background",
        "crop_image",
        "convert_format",
        "optimize_image",
        "resize_image",
        "vectorize_image",
    ]
    params: dict = Field(
        default_factory=dict,
        description="Parameters for the operation (same as individual tool params, minus image_path).",
    )


class BatchProcessInput(BaseModel):
    """Input for the batch_process tool."""

    image_path: str = Field(
        description="Path to the input image file (relative to workspace or allowed path)"
    )
    steps: list[BatchStep] = Field(
        description="Ordered list of processing steps to apply sequentially.",
        min_length=1,
    )
    output_path: str | None = Field(
        default=None,
        description="Final output path. Intermediate files are cleaned up.",
    )


class BatchProcessOutput(BaseModel):
    """Output from the batch_process tool."""

    success: bool
    final_image: ImageMetadata
    steps_completed: int
    total_steps: int
    original_size_bytes: int
    total_reduction_percent: float
    total_processing_time_ms: int
    step_results: list[dict] = Field(
        description="Summary of each step's result.",
    )


# ============================================================================
# list_models / get_model_info
# ============================================================================


class ModelInfo(BaseModel):
    """Information about a single model."""

    model_id: str
    name: str
    description: str
    is_loaded: bool
    ttl_seconds: int


class ListModelsOutput(BaseModel):
    """Output from the list_models tool."""

    models: list[ModelInfo]
    total: int


class GetModelInfoOutput(BaseModel):
    """Output from the get_model_info tool."""

    model: ModelInfo


# ============================================================================
# save_image (path-only file management)
# ============================================================================


class SaveImageOutput(BaseModel):
    """Output from the save_image tool."""

    success: bool
    source_path: str = Field(description="Original source path (relative)")
    saved_path: str = Field(description="Destination path where image was saved/copied (relative)")
    file_size_bytes: int = Field(description="File size in bytes")
    file_size_human: str = Field(description="Human-readable file size")
    message: str = Field(default="Image saved successfully")
