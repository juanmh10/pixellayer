"""
Configuration
==============
Global configuration with environment variable overrides.
"""

from __future__ import annotations

import os
from pathlib import Path


def _get_env(key: str, default: str = "") -> str:
    """Read environment variable with PIXELLAYER_ prefix first, falling back to IMGCUT_."""
    val = os.getenv(f"PIXELLAYER_{key}")
    if val is not None:
        return val
    return os.getenv(f"IMGCUT_{key}", default)


class Config:
    """Application configuration. Values can be overridden via environment variables."""

    # Model settings
    DEFAULT_MODEL: str = _get_env("DEFAULT_MODEL", "birefnet-general")
    MODEL_TTL_SECONDS: int = int(_get_env("MODEL_TTL", "300"))
    MODELS_CACHE_DIR: Path = Path(
        _get_env("MODELS_CACHE", str(Path(__file__).parent.parent.parent / "models_cache"))
    )

    # Processing defaults
    DEFAULT_WEBP_QUALITY: int = int(_get_env("WEBP_QUALITY", "90"))
    DEFAULT_JPEG_QUALITY: int = int(_get_env("JPEG_QUALITY", "85"))
    MAX_IMAGE_PIXELS: int = int(_get_env("MAX_PIXELS", str(50_000_000)))  # ~7000x7000
    INFERENCE_TIMEOUT: int = int(_get_env("INFERENCE_TIMEOUT", "60"))  # timeout in seconds
    FORCE_LOCAL_FILES: bool = _get_env("FORCE_LOCAL_FILES", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # Security
    ALLOWED_WORKSPACES: list[Path] = [
        Path(p.strip()).resolve()
        for p in _get_env("ALLOWED_WORKSPACES", "").split(";")
        if p.strip()
    ]

    def get_allowed_workspaces(self) -> list[Path]:
        """Return allowed workspace paths sorted by descending path length (deepest first).

        If no workspaces are configured, defaults strictly to the current working
        directory (strict workspace jail) to prevent path traversal and arbitrary access.
        """
        workspaces = list(self.ALLOWED_WORKSPACES)
        if not workspaces:
            workspaces = [
                Path(p.strip()).resolve()
                for p in _get_env("ALLOWED_WORKSPACES", "").split(";")
                if p.strip()
            ]
        if not workspaces:
            workspaces = [Path.cwd().resolve()]
        return sorted(workspaces, key=lambda p: len(str(p)), reverse=True)

    def get_models_cache_dir(self) -> Path:
        """Resolve models cache directory with standard OS cache fallback."""
        env_cache = _get_env("MODELS_CACHE", "")
        if env_cache:
            return Path(env_cache).resolve()
        repo_cache = Path(__file__).parent.parent.parent / "models_cache"
        if repo_cache.exists():
            return repo_cache.resolve()
        user_cache = Path.home() / ".cache" / "pixellayer" / "models"
        user_cache.mkdir(parents=True, exist_ok=True)
        return user_cache

    # Logging & Paths
    LOG_DIR: Path = Path(_get_env("LOG_DIR", str(Path(__file__).parent.parent.parent / "logs")))
    LOG_FILE: Path = Path(
        _get_env("LOG_FILE", str(Path(__file__).parent.parent.parent / "logs" / "pixellayer.log"))
    )

    # Server & Transport settings
    HOST: str = _get_env("HOST", "127.0.0.1")
    PORT: int = int(_get_env("PORT", "8000"))
    TRANSPORT: str = _get_env("TRANSPORT", "stdio")  # stdio, sse, streamable-http
    ALLOWED_HOSTS: list[str] = [
        h.strip()
        for h in _get_env("ALLOWED_HOSTS", "127.0.0.1:*;localhost:*;[::1]:*").split(";")
        if h.strip()
    ]
    ENABLE_DNS_REBINDING: bool = _get_env("ENABLE_DNS_REBINDING", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    ALLOWED_ORIGINS: list[str] = [
        o.strip()
        for o in _get_env(
            "ALLOWED_ORIGINS",
            "http://127.0.0.1:*;http://localhost:*;http://[::1]:*",
        ).split(";")
        if o.strip()
    ]

    # Device
    DEVICE: str = _get_env("DEVICE", "auto")  # auto, cpu, cuda, mps

    @classmethod
    def get_device(cls) -> str:
        """Resolve 'auto' device to actual device string."""
        if cls.DEVICE != "auto":
            return cls.DEVICE
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"


config = Config()
