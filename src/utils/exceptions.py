"""
Custom Exceptions
==================
Structured error types for clear error reporting through MCP.
"""

from __future__ import annotations


class ImgCutError(Exception):
    """Base exception for all img-cut errors."""

    def __init__(self, message: str, code: str = "UNKNOWN_ERROR") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class FileNotFoundError_(ImgCutError):
    """Input file does not exist."""

    def __init__(self, path: str) -> None:
        super().__init__(
            message=f"File not found: '{path}'",
            code="FILE_NOT_FOUND",
        )


class UnsupportedFormatError(ImgCutError):
    """Image format is not supported."""

    def __init__(self, format_: str, supported: list[str]) -> None:
        super().__init__(
            message=f"Unsupported format '{format_}'. Supported: {', '.join(supported)}",
            code="UNSUPPORTED_FORMAT",
        )


class ModelNotFoundError(ImgCutError):
    """Requested model is not registered."""

    def __init__(self, model_id: str, available: list[str]) -> None:
        super().__init__(
            message=f"Model '{model_id}' not found. Available: {', '.join(available)}",
            code="MODEL_NOT_FOUND",
        )


class ModelLoadError(ImgCutError):
    """Model failed to load."""

    def __init__(self, model_id: str, reason: str) -> None:
        super().__init__(
            message=f"Failed to load model '{model_id}': {reason}",
            code="MODEL_LOAD_ERROR",
        )


class ProcessingError(ImgCutError):
    """Image processing failed."""

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            message=f"Processing failed during '{operation}': {reason}",
            code="PROCESSING_ERROR",
        )


class SecurityError(ImgCutError):
    """Security restriction violated (e.g., path traversal)."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Security error: {reason}",
            code="SECURITY_ERROR",
        )


class TimeoutError_(ImgCutError):
    """Operation timed out."""

    def __init__(self, operation: str, timeout_seconds: int) -> None:
        super().__init__(
            message=f"Operation '{operation}' timed out after {timeout_seconds}s",
            code="TIMEOUT",
        )
