"""
Contract Schema Tests
======================
Validates that all Pydantic schemas serialize and deserialize correctly.
Tests enum values, field constraints, and model_dump() output.
"""

from __future__ import annotations

from src.contracts.schemas import (
    BatchStep,
    ImageFormat,
    ImageMetadata,
    ListModelsOutput,
    ModelInfo,
    OptimizationLevel,
    RemoveBackgroundInput,
    RemoveBackgroundOutput,
    ResampleFilter,
    ResizeImageInput,
    ResizeMode,
    VectorDetailLevel,
)


class TestEnums:
    """Test enum values are valid strings."""

    def test_image_format_values(self) -> None:
        assert ImageFormat.PNG == "png"
        assert ImageFormat.WEBP == "webp"
        assert ImageFormat.JPEG == "jpeg"

    def test_resize_mode_values(self) -> None:
        assert ResizeMode.FIT == "fit"
        assert ResizeMode.FILL == "fill"
        assert ResizeMode.EXACT == "exact"
        assert ResizeMode.PERCENTAGE == "percentage"

    def test_resample_filter_values(self) -> None:
        assert ResampleFilter.LANCZOS == "lanczos"
        assert ResampleFilter.BICUBIC == "bicubic"

    def test_optimization_level_values(self) -> None:
        assert OptimizationLevel.LOSSLESS == "lossless"
        assert OptimizationLevel.AGGRESSIVE == "aggressive"

    def test_vector_detail_level_values(self) -> None:
        assert VectorDetailLevel.LOW == "low"
        assert VectorDetailLevel.HIGH == "high"


class TestImageMetadata:
    """Test ImageMetadata schema."""

    def test_valid_metadata(self) -> None:
        meta = ImageMetadata(
            file_path="/test/output.png",
            format="png",
            width=800,
            height=600,
            file_size_bytes=102400,
            file_size_human="100.0 KB",
        )
        assert meta.file_path == "/test/output.png"
        assert meta.width == 800
        assert meta.height == 600

    def test_metadata_serialization(self) -> None:
        meta = ImageMetadata(
            file_path="/test/output.png",
            format="png",
            width=800,
            height=600,
            file_size_bytes=102400,
            file_size_human="100.0 KB",
        )
        data = meta.model_dump()
        assert isinstance(data, dict)
        assert data["file_path"] == "/test/output.png"
        assert data["file_size_bytes"] == 102400


class TestRemoveBackgroundInput:
    """Test RemoveBackgroundInput defaults and validation."""

    def test_defaults(self) -> None:
        inp = RemoveBackgroundInput(image_path="/test/photo.jpg")
        assert inp.model == "birefnet-general"
        assert inp.output_path is None
        assert inp.output_format == ImageFormat.PNG

    def test_custom_model(self) -> None:
        inp = RemoveBackgroundInput(
            image_path="/test/photo.jpg",
            model="birefnet-portrait",
        )
        assert inp.model == "birefnet-portrait"


class TestRemoveBackgroundOutput:
    """Test RemoveBackgroundOutput serialization."""

    def test_valid_output(self) -> None:
        output = RemoveBackgroundOutput(
            success=True,
            image=ImageMetadata(
                file_path="/test/output_nobg.png",
                format="png",
                width=800,
                height=600,
                file_size_bytes=204800,
                file_size_human="200.0 KB",
            ),
            model_used="birefnet-general",
            processing_time_ms=2500,
            original_size_bytes=307200,
            reduction_percent=33.33,
        )
        data = output.model_dump()
        assert data["success"] is True
        assert data["model_used"] == "birefnet-general"
        assert data["image"]["file_path"] == "/test/output_nobg.png"


class TestResizeImageInput:
    """Test ResizeImageInput validation."""

    def test_defaults(self) -> None:
        inp = ResizeImageInput(image_path="/test/photo.jpg", width=800)
        assert inp.mode == ResizeMode.FIT
        assert inp.resample == ResampleFilter.LANCZOS
        assert inp.height is None

    def test_percentage_mode(self) -> None:
        inp = ResizeImageInput(
            image_path="/test/photo.jpg",
            scale_percent=50.0,
        )
        assert inp.scale_percent == 50.0


class TestBatchStep:
    """Test BatchStep validation."""

    def test_valid_step(self) -> None:
        step = BatchStep(
            operation="remove_background",
            params={"model": "birefnet-general"},
        )
        assert step.operation == "remove_background"
        assert step.params["model"] == "birefnet-general"

    def test_empty_params(self) -> None:
        step = BatchStep(operation="convert_format")
        assert step.params == {}


class TestModelInfo:
    """Test ModelInfo schema."""

    def test_valid_model_info(self) -> None:
        info = ModelInfo(
            model_id="birefnet-general",
            name="BiRefNet General",
            description="General purpose model",
            is_loaded=False,
            ttl_seconds=300,
        )
        assert info.is_loaded is False
        assert info.ttl_seconds == 300

    def test_list_models_output(self) -> None:
        models = [
            ModelInfo(
                model_id=f"model-{i}",
                name=f"Model {i}",
                description=f"Test model {i}",
                is_loaded=False,
                ttl_seconds=300,
            )
            for i in range(3)
        ]
        output = ListModelsOutput(models=models, total=3)
        assert output.total == 3
        assert len(output.models) == 3

    def test_save_image_output(self) -> None:
        from src.contracts.schemas import SaveImageOutput

        out = SaveImageOutput(
            success=True,
            source_path="input/foto.png",
            saved_path="output/foto.png",
            file_size_bytes=1024,
            file_size_human="1.0 KB",
        )
        assert out.success is True
        assert out.saved_path == "output/foto.png"
