"""
Configuration
==============
Global configuration with environment variable overrides.
"""

from __future__ import annotations

import os
from pathlib import Path


class Config:
    """Application configuration. Values can be overridden via environment variables."""

    # Model settings
    DEFAULT_MODEL: str = os.getenv("IMGCUT_DEFAULT_MODEL", "birefnet-general")
    MODEL_TTL_SECONDS: int = int(os.getenv("IMGCUT_MODEL_TTL", "300"))
    MODELS_CACHE_DIR: Path = Path(
        os.getenv("IMGCUT_MODELS_CACHE", str(Path(__file__).parent.parent.parent / "models_cache"))
    )

    # Processing defaults
    DEFAULT_WEBP_QUALITY: int = int(os.getenv("IMGCUT_WEBP_QUALITY", "90"))
    DEFAULT_JPEG_QUALITY: int = int(os.getenv("IMGCUT_JPEG_QUALITY", "85"))
    MAX_IMAGE_PIXELS: int = int(os.getenv("IMGCUT_MAX_PIXELS", str(50_000_000)))  # ~7000x7000
    INFERENCE_TIMEOUT: int = int(os.getenv("IMGCUT_INFERENCE_TIMEOUT", "60"))  # timeout in seconds
    FORCE_LOCAL_FILES: bool = os.getenv("IMGCUT_FORCE_LOCAL_FILES", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # Security
    ALLOWED_WORKSPACES: list[Path] = [
        Path(p.strip()).resolve()
        for p in os.getenv("IMGCUT_ALLOWED_WORKSPACES", "").split(";")
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
                for p in os.getenv("IMGCUT_ALLOWED_WORKSPACES", "").split(";")
                if p.strip()
            ]
        if not workspaces:
            workspaces = [Path.cwd().resolve()]
        return sorted(workspaces, key=lambda p: len(str(p)), reverse=True)

    def get_models_cache_dir(self) -> Path:
        """Resolve models cache directory with standard OS cache fallback."""
        env_cache = os.getenv("IMGCUT_MODELS_CACHE")
        if env_cache:
            return Path(env_cache).resolve()
        repo_cache = Path(__file__).parent.parent.parent / "models_cache"
        if repo_cache.exists():
            return repo_cache.resolve()
        user_cache = Path.home() / ".cache" / "img-cut" / "models"
        user_cache.mkdir(parents=True, exist_ok=True)
        return user_cache

    # Logging & Paths
    LOG_DIR: Path = Path(
        os.getenv("IMGCUT_LOG_DIR", str(Path(__file__).parent.parent.parent / "logs"))
    )
    LOG_FILE: Path = Path(
        os.getenv(
            "IMGCUT_LOG_FILE", str(Path(__file__).parent.parent.parent / "logs" / "img-cut.log")
        )
    )

    # Device
    DEVICE: str = os.getenv("IMGCUT_DEVICE", "auto")  # auto, cpu, cuda, mps

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
