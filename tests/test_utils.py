"""
Utility Tests
==============
Tests for file utilities, config, and exceptions.
"""

from __future__ import annotations

from pathlib import Path

from src.utils.config import Config
from src.utils.exceptions import (
    FileNotFoundError_,
    ImgCutError,
    ModelLoadError,
    ModelNotFoundError,
    ProcessingError,
    UnsupportedFormatError,
)
from src.utils.files import (
    calculate_reduction,
    generate_output_path,
    human_readable_size,
    to_safe_relative_path,
)


class TestToSafeRelativePath:
    """Test safe relative path conversion."""

    def test_relative_within_workspace(self, monkeypatch) -> None:
        from src.utils.config import config

        workspace = Path("/workspace/test")
        monkeypatch.setattr(config, "ALLOWED_WORKSPACES", [workspace])

        rel = to_safe_relative_path("/workspace/test/output/image.png")
        assert rel == "output/image.png"

    def test_relative_fallback(self) -> None:
        p = Path.cwd() / "output" / "image.svg"
        rel = to_safe_relative_path(p)
        assert rel == "output/image.svg"


class TestHumanReadableSize:
    """Test file size formatting."""

    def test_bytes(self) -> None:
        assert human_readable_size(500) == "500.0 B"

    def test_kilobytes(self) -> None:
        assert human_readable_size(1024) == "1.0 KB"

    def test_megabytes(self) -> None:
        assert human_readable_size(1_048_576) == "1.0 MB"

    def test_gigabytes(self) -> None:
        assert human_readable_size(1_073_741_824) == "1.0 GB"

    def test_zero(self) -> None:
        assert human_readable_size(0) == "0 B"

    def test_fractional_kb(self) -> None:
        assert human_readable_size(1536) == "1.5 KB"


class TestGenerateOutputPath:
    """Test output path generation."""

    def test_default_suffix(self) -> None:
        result = generate_output_path(Path("/test/image.png"))
        assert result == Path("/test/image_processed.png")

    def test_custom_suffix(self) -> None:
        result = generate_output_path(Path("/test/image.png"), suffix="_nobg")
        assert result == Path("/test/image_nobg.png")

    def test_custom_extension(self) -> None:
        result = generate_output_path(
            Path("/test/image.png"),
            suffix="_converted",
            extension="webp",
        )
        assert result == Path("/test/image_converted.webp")

    def test_no_suffix(self) -> None:
        result = generate_output_path(Path("/test/image.png"), suffix="")
        assert result == Path("/test/image.png")


class TestCalculateReduction:
    """Test size reduction calculation."""

    def test_reduction(self) -> None:
        assert calculate_reduction(1000, 700) == 30.0

    def test_increase(self) -> None:
        assert calculate_reduction(700, 1000) == -42.86

    def test_same_size(self) -> None:
        assert calculate_reduction(1000, 1000) == 0.0

    def test_zero_original(self) -> None:
        assert calculate_reduction(0, 100) == 0.0


class TestExceptions:
    """Test custom exception hierarchy."""

    def test_base_error(self) -> None:
        err = ImgCutError("test error", "TEST_CODE")
        assert str(err) == "test error"
        assert err.code == "TEST_CODE"

    def test_file_not_found(self) -> None:
        err = FileNotFoundError_("/missing/file.png")
        assert err.code == "FILE_NOT_FOUND"
        assert "/missing/file.png" in err.message

    def test_unsupported_format(self) -> None:
        err = UnsupportedFormatError(".bmp", [".png", ".webp"])
        assert err.code == "UNSUPPORTED_FORMAT"
        assert ".bmp" in err.message

    def test_model_not_found(self) -> None:
        err = ModelNotFoundError("bad-model", ["birefnet-general"])
        assert err.code == "MODEL_NOT_FOUND"

    def test_model_load_error(self) -> None:
        err = ModelLoadError("birefnet-general", "out of memory")
        assert err.code == "MODEL_LOAD_ERROR"
        assert "out of memory" in err.message

    def test_processing_error(self) -> None:
        err = ProcessingError("resize", "invalid dimensions")
        assert err.code == "PROCESSING_ERROR"

    def test_all_inherit_from_base(self) -> None:
        errors = [
            FileNotFoundError_("/test"),
            UnsupportedFormatError(".xyz", []),
            ModelNotFoundError("x", []),
            ModelLoadError("x", "y"),
            ProcessingError("x", "y"),
        ]
        for err in errors:
            assert isinstance(err, ImgCutError)

    def test_timeout_error(self) -> None:
        from src.utils.exceptions import TimeoutError_

        err = TimeoutError_("test_inference", 30)
        assert err.code == "TIMEOUT"
        assert "30s" in err.message
        assert isinstance(err, ImgCutError)


class TestConfig:
    """Test configuration module."""

    def test_default_model(self) -> None:
        assert Config.DEFAULT_MODEL == "birefnet-general"

    def test_default_ttl(self) -> None:
        assert Config.MODEL_TTL_SECONDS == 300

    def test_models_cache_dir_is_path(self) -> None:
        assert isinstance(Config.MODELS_CACHE_DIR, Path)

    def test_get_device_returns_string(self) -> None:
        device = Config.get_device()
        assert isinstance(device, str)
        assert device in ("cpu", "cuda", "mps")

    def test_inference_timeout_and_local_files_config(self) -> None:
        assert isinstance(Config.INFERENCE_TIMEOUT, int)
        assert Config.INFERENCE_TIMEOUT > 0
        assert isinstance(Config.FORCE_LOCAL_FILES, bool)


class TestFileCopySafe:
    """Test path-only copy operation."""

    def test_copy_file_safe(self, tmp_path: Path) -> None:
        from src.utils.files import copy_file_safe

        src_file = tmp_path / "origin.png"
        src_file.write_text("dummy image data")
        dst_file = tmp_path / "subfolder" / "dest.png"

        result = copy_file_safe(src_file, dst_file)
        assert result.exists()
        assert result.read_text() == "dummy image data"


class TestSafePathResolution:
    """Test safe path resolution, jail enforcement, and anti-traversal."""

    def test_block_path_traversal(self, tmp_path: Path, monkeypatch) -> None:
        import pytest

        from src.utils.config import config
        from src.utils.exceptions import SecurityError
        from src.utils.files import resolve_safe_path

        ws = tmp_path / "workspace"
        ws.mkdir()
        monkeypatch.setattr(config, "ALLOWED_WORKSPACES", [ws])

        with pytest.raises(SecurityError) as exc_info:
            resolve_safe_path(ws / ".." / "outside.png")
        assert "Access denied" in str(exc_info.value)
        assert "outside.png" in str(exc_info.value)

    def test_resolve_relative_in_allowed_workspace(self, tmp_path: Path, monkeypatch) -> None:
        from src.utils.config import config
        from src.utils.files import resolve_safe_path

        ws1 = tmp_path / "ws1"
        ws2 = tmp_path / "ws2"
        ws1.mkdir()
        ws2.mkdir()
        monkeypatch.setattr(config, "ALLOWED_WORKSPACES", [ws1, ws2])

        target_file = ws2 / "sample.png"
        target_file.write_text("img")

        resolved = resolve_safe_path("sample.png")
        assert resolved == str(target_file.resolve())

    def test_zero_host_path_leak_on_file_not_found(self, tmp_path: Path, monkeypatch) -> None:
        import pytest

        from src.utils.config import config
        from src.utils.exceptions import FileNotFoundError_
        from src.utils.files import resolve_safe_path

        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setattr(config, "ALLOWED_WORKSPACES", [ws])

        with pytest.raises(FileNotFoundError_) as exc_info:
            resolve_safe_path("non_existent_img.png")
        assert "File not found: 'non_existent_img.png'" in str(exc_info.value)
