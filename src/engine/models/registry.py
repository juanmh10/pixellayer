"""
Model Registry
================
Singleton registry that manages all available models.
Provides model discovery (list/info) WITHOUT loading weights.
Handles model lifecycle (load, predict, unload).
"""

from __future__ import annotations

import logging
from typing import Any

from src.engine.models.base import BaseModel
from src.utils.exceptions import ModelNotFoundError

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Central registry for all available segmentation models.

    Models are registered at import time but NOT loaded.
    Loading only happens when predict() is called.
    """

    def __init__(self) -> None:
        self._models: dict[str, BaseModel] = {}

    def register(self, model: BaseModel) -> None:
        """Register a model wrapper (does NOT load weights)."""
        self._models[model.model_id] = model
        logger.debug(f"Registered model: {model.model_id}")

    def ensure_defaults(self) -> None:
        """Ensure standard models are registered if registry is empty."""
        if not self._models:
            from src.engine.models.birefnet import create_birefnet_models
            from src.engine.models.isnet import create_isnet_model
            from src.engine.models.rmbg import create_rmbg_model

            for model in create_birefnet_models():
                self.register(model)
            self.register(create_rmbg_model())
            self.register(create_isnet_model())

    def get(self, model_id: str) -> BaseModel:
        """Get a model by ID. Raises ModelNotFoundError if not found."""
        if model_id not in self._models:
            self.ensure_defaults()
        if model_id not in self._models:
            raise ModelNotFoundError(
                model_id=model_id,
                available=list(self._models.keys()),
            )
        return self._models[model_id]

    def list_models(self) -> list[dict[str, Any]]:
        """List all registered models with metadata (no loading)."""
        self.ensure_defaults()
        return [model.get_info() for model in self._models.values()]

    def get_model_info(self, model_id: str) -> dict[str, Any]:
        """Get detailed info for a specific model (no loading)."""
        return self.get(model_id).get_info()

    def unload_all(self) -> None:
        """Unload all models from memory."""
        for model in self._models.values():
            model.unload()


# Global singleton — populated during server initialization
registry = ModelRegistry()
