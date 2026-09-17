"""
Base Model Interface
=====================
Abstract base class for all background removal models.
Defines the contract that every model wrapper must implement.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)


class BaseModel(ABC):
    """Abstract base for all segmentation model wrappers.

    Implements lazy loading with TTL-based auto-unload.
    Subclasses only need to implement _load_model() and _predict_mask().
    """

    def __init__(
        self,
        model_id: str,
        name: str,
        description: str,
        ttl_seconds: int = 300,  # 5 minutes default
    ) -> None:
        self.model_id = model_id
        self.name = name
        self.description = description
        self.ttl_seconds = ttl_seconds

        self._model: Any = None
        self._last_used: float = 0.0
        self._lock = threading.RLock()
        self._unload_timer: threading.Timer | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if model weights are currently in memory."""
        return self._model is not None

    def ensure_loaded(self) -> None:
        """Load model if not already loaded. Thread-safe."""
        with self._lock:
            if self._model is None:
                logger.info(f"Loading model '{self.model_id}'...")
                start = time.monotonic()
                self._model = self._load_model()
                elapsed = time.monotonic() - start
                logger.info(f"Model '{self.model_id}' loaded in {elapsed:.1f}s")
            self._last_used = time.monotonic()
            self._schedule_unload()

    def unload(self) -> None:
        """Unload model from memory."""
        with self._lock:
            if self._model is not None:
                logger.info(f"Unloading model '{self.model_id}'...")
                self._model = None
                if self._unload_timer:
                    self._unload_timer.cancel()
                    self._unload_timer = None

    def _schedule_unload(self) -> None:
        """Schedule auto-unload after TTL expires."""
        if self._unload_timer:
            self._unload_timer.cancel()

        def _check_and_unload() -> None:
            with self._lock:
                if self._model is not None:
                    idle_time = time.monotonic() - self._last_used
                    if idle_time >= self.ttl_seconds:
                        logger.info(
                            f"Model '{self.model_id}' idle for {idle_time:.0f}s, unloading..."
                        )
                        self.unload()

        self._unload_timer = threading.Timer(self.ttl_seconds, _check_and_unload)
        self._unload_timer.daemon = True
        self._unload_timer.start()

    def predict(self, image: Image.Image) -> Image.Image:
        """Run inference to produce an alpha mask.

        Args:
            image: Input PIL Image (RGB).

        Returns:
            PIL Image with RGBA channels (transparent background).
        """
        import concurrent.futures

        from src.utils.config import config
        from src.utils.exceptions import TimeoutError_

        self.ensure_loaded()
        self._last_used = time.monotonic()

        timeout_sec = config.INFERENCE_TIMEOUT
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._predict_mask, image)
            try:
                return future.result(timeout=timeout_sec)
            except concurrent.futures.TimeoutError as exc:
                logger.error(
                    f"Inference for model '{self.model_id}' timed out after {timeout_sec}s"
                )
                raise TimeoutError_(
                    operation=f"model_{self.model_id}_predict",
                    timeout_seconds=timeout_sec,
                ) from exc

    @abstractmethod
    def _load_model(self) -> Any:
        """Load model weights into memory. Called once on first use."""
        ...

    @abstractmethod
    def _predict_mask(self, image: Image.Image) -> Image.Image:
        """Generate alpha mask from input image.

        Args:
            image: Input PIL Image (RGB).

        Returns:
            PIL Image in RGBA mode with transparent background.
        """
        ...

    def get_info(self) -> dict[str, Any]:
        """Return model metadata without loading weights."""
        return {
            "model_id": self.model_id,
            "name": self.name,
            "description": self.description,
            "is_loaded": self.is_loaded,
            "ttl_seconds": self.ttl_seconds,
        }
