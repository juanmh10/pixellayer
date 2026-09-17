"""
RMBG-2.0 Model Wrapper
========================
Wraps BRIA RMBG-2.0 for commercial-friendly background removal.
Uses BiRefNet architecture with BRIA's curated, fully-licensed training data.

RMBG-2.0 provides excellent general-purpose performance and is ideal
for production workflows where data licensing is a concern.
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

RMBG_HF_ID = "briaai/RMBG-2.0"
RMBG_INPUT_SIZE = (1024, 1024)


class RMBGModel(BaseModel):
    """BRIA RMBG-2.0 model wrapper.

    Commercial-friendly background removal using BiRefNet architecture
    trained on BRIA's curated dataset.
    """

    def __init__(self, ttl_seconds: int | None = None) -> None:
        super().__init__(
            model_id="rmbg-2.0",
            name="RMBG 2.0",
            description=(
                "BRIA RMBG-2.0 — Commercial-friendly background removal. "
                "Built on BiRefNet architecture with fully-licensed training data. "
                "Great for production and commercial use."
            ),
            ttl_seconds=ttl_seconds or config.MODEL_TTL_SECONDS,
        )
        self._device: str = ""
        self._transform: transforms.Compose | None = None

    def _load_model(self) -> Any:
        """Load RMBG-2.0 from HuggingFace."""
        from transformers import AutoModelForImageSegmentation

        self._device = config.get_device()
        logger.info(f"Loading RMBG-2.0 on device '{self._device}'...")

        try:
            model = AutoModelForImageSegmentation.from_pretrained(
                RMBG_HF_ID,
                trust_remote_code=True,
                cache_dir=str(config.MODELS_CACHE_DIR),
                local_files_only=config.FORCE_LOCAL_FILES,
            )
        except Exception as e:
            if config.FORCE_LOCAL_FILES:
                logger.warning(
                    f"Failed local-only load for {RMBG_HF_ID} ({e}), falling back to online fetch..."
                )
                model = AutoModelForImageSegmentation.from_pretrained(
                    RMBG_HF_ID,
                    trust_remote_code=True,
                    cache_dir=str(config.MODELS_CACHE_DIR),
                    local_files_only=False,
                )
            else:
                raise
        model = model.float().to(self._device)
        model.eval()

        self._transform = transforms.Compose(
            [
                transforms.Resize(
                    RMBG_INPUT_SIZE, interpolation=transforms.InterpolationMode.BILINEAR
                ),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

        logger.info("RMBG-2.0 loaded successfully")
        return model

    def _predict_mask(self, image: Image.Image) -> Image.Image:
        """Generate RGBA image with transparent background using RMBG-2.0.

        Args:
            image: Input PIL Image.

        Returns:
            PIL Image in RGBA mode with transparent background.
        """
        original_rgb = image.convert("RGB")
        original_size = original_rgb.size

        input_tensor = self._transform(original_rgb).unsqueeze(0).to(self._device)

        with torch.no_grad():
            preds = self._model(input_tensor)

        # RMBG-2.0 follows same output pattern as BiRefNet
        if isinstance(preds, (list, tuple)):
            pred = preds[-1]
        else:
            pred = preds

        if isinstance(pred, (list, tuple)):
            pred = pred[-1]

        pred = torch.sigmoid(pred)
        pred = pred.squeeze(0).squeeze(0).cpu()

        mask_np = pred.numpy()
        mask_pil = Image.fromarray((mask_np * 255).astype(np.uint8), mode="L")
        mask_pil = mask_pil.resize(original_size, Image.BILINEAR)

        rgba = original_rgb.copy()
        rgba.putalpha(mask_pil)

        return rgba

    def unload(self) -> None:
        """Unload model and free GPU memory."""
        super().unload()
        self._transform = None
        self._device = ""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def get_info(self) -> dict[str, Any]:
        """Return model metadata."""
        info = super().get_info()
        info["hf_id"] = RMBG_HF_ID
        info["input_size"] = list(RMBG_INPUT_SIZE)
        info["device"] = self._device or config.get_device()
        info["license"] = "commercial-friendly"
        return info


def create_rmbg_model() -> RMBGModel:
    """Factory function to create RMBG-2.0 instance (no weight loading)."""
    return RMBGModel()
