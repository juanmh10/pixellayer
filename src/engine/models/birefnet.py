"""
BiRefNet Model Wrapper
=======================
Wraps BiRefNet variants for background removal via HuggingFace transformers.
Supports: general, portrait, matting, hr variants.

Each variant is a separate instance with its own HuggingFace checkpoint.
Models are lazy-loaded on first inference and auto-unloaded after TTL.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import torch
from PIL import Image
from torchvision import transforms

from src.engine.models.base import BaseModel
from src.utils.config import config

logger = logging.getLogger(__name__)

# HuggingFace model IDs for each BiRefNet variant
BIREFNET_VARIANTS: dict[str, dict[str, str]] = {
    "birefnet-general": {
        "hf_id": "ZhengPeng7/BiRefNet",
        "name": "BiRefNet General",
        "description": "General purpose, high quality background removal. Best all-around model.",
    },
    "birefnet-portrait": {
        "hf_id": "ZhengPeng7/BiRefNet-portrait",
        "name": "BiRefNet Portrait",
        "description": "Optimized for human subjects and portraits. Best for people photos.",
    },
    "birefnet-matting": {
        "hf_id": "ZhengPeng7/BiRefNet-matting",
        "name": "BiRefNet Matting",
        "description": "Fine hair, fur, and semi-transparent edges. Best for complex edges.",
    },
    "birefnet-hr": {
        "hf_id": "ZhengPeng7/BiRefNet-massive",
        "name": "BiRefNet High Resolution",
        "description": "Designed for high-resolution images (4K+). Heavier but sharper.",
    },
}

# Standard input size for BiRefNet models
BIREFNET_INPUT_SIZE = (1024, 1024)


class BiRefNetModel(BaseModel):
    """BiRefNet model wrapper for background removal.

    Loads model weights from HuggingFace on first use.
    Produces RGBA output with clean alpha channel — no fill, no padding.
    """

    def __init__(
        self,
        model_id: str,
        hf_id: str,
        name: str,
        description: str,
        ttl_seconds: int | None = None,
    ) -> None:
        super().__init__(
            model_id=model_id,
            name=name,
            description=description,
            ttl_seconds=ttl_seconds or config.MODEL_TTL_SECONDS,
        )
        self.hf_id = hf_id
        self._device: str = ""
        self._transform: transforms.Compose | None = None

    def _load_model(self) -> Any:
        """Load BiRefNet from HuggingFace transformers.

        Uses AutoModelForImageSegmentation which handles the BiRefNet architecture
        automatically when trust_remote_code=True.
        """
        # Lazy import to avoid loading torch at server startup
        from transformers import AutoModelForImageSegmentation

        self._device = config.get_device()
        logger.info(f"Loading {self.hf_id} on device '{self._device}'...")

        # If cache exists or FORCE_LOCAL_FILES is set, try local_files_only first to prevent network delay/hangs
        try:
            model = AutoModelForImageSegmentation.from_pretrained(
                self.hf_id,
                trust_remote_code=True,
                cache_dir=str(config.MODELS_CACHE_DIR),
                local_files_only=config.FORCE_LOCAL_FILES,
            )
        except Exception as e:
            if config.FORCE_LOCAL_FILES:
                logger.warning(
                    f"Failed local-only load for {self.hf_id} ({e}), falling back to online fetch..."
                )
                model = AutoModelForImageSegmentation.from_pretrained(
                    self.hf_id,
                    trust_remote_code=True,
                    cache_dir=str(config.MODELS_CACHE_DIR),
                    local_files_only=False,
                )
            else:
                raise
        model = model.float().to(self._device)
        model.eval()

        # Setup preprocessing transform
        self._transform = transforms.Compose(
            [
                transforms.Resize(
                    BIREFNET_INPUT_SIZE, interpolation=transforms.InterpolationMode.BILINEAR
                ),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

        logger.info(f"Model {self.model_id} loaded successfully on {self._device}")
        return model

    def _predict_mask(self, image: Image.Image) -> Image.Image:
        """Generate RGBA image with transparent background.

        Args:
            image: Input PIL Image (any mode, will be converted to RGB).

        Returns:
            PIL Image in RGBA mode with transparent background.
            Original RGB channels preserved, alpha from predicted mask.
        """
        # Ensure RGB input
        original_rgb = image.convert("RGB")
        original_size = original_rgb.size  # (width, height)

        # Preprocess
        input_tensor = self._transform(original_rgb).unsqueeze(0).to(self._device)

        # Inference
        with torch.no_grad():
            preds = self._model(input_tensor)

        # BiRefNet returns a list of predictions at different scales
        # The last one is the finest/final prediction
        if isinstance(preds, (list, tuple)):
            pred = preds[-1]
        else:
            pred = preds

        # Handle nested sigmoid outputs
        if isinstance(pred, (list, tuple)):
            pred = pred[-1]

        # Apply sigmoid to get probabilities [0, 1]
        pred = torch.sigmoid(pred)

        # Remove batch dimension and move to CPU
        pred = pred.squeeze(0).squeeze(0).cpu()

        # Convert to numpy and resize to original dimensions
        mask_np = pred.numpy()

        # Resize mask back to original image size
        mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8), mode="L")
        mask_pil = mask_pil.resize(original_size, Image.BILINEAR)

        # Compose RGBA: original RGB + predicted alpha
        rgba = original_rgb.copy()
        rgba.putalpha(mask_pil)

        return rgba

    def unload(self) -> None:
        """Unload model and free GPU memory."""
        super().unload()
        self._transform = None
        self._device = ""
        # Force GPU memory cleanup
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def get_info(self) -> dict[str, Any]:
        """Return model metadata including HuggingFace ID."""
        info = super().get_info()
        info["hf_id"] = self.hf_id
        info["input_size"] = list(BIREFNET_INPUT_SIZE)
        info["device"] = self._device or config.get_device()
        return info


def create_birefnet_models() -> list[BiRefNetModel]:
    """Factory function to create all BiRefNet variant instances.

    Returns model wrappers — does NOT load any weights.
    """
    models: list[BiRefNetModel] = []
    for model_id, variant_info in BIREFNET_VARIANTS.items():
        model = BiRefNetModel(
            model_id=model_id,
            hf_id=variant_info["hf_id"],
            name=variant_info["name"],
            description=variant_info["description"],
        )
        models.append(model)
    return models
