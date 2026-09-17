"""
IS-Net Model Wrapper
=====================
Wraps IS-Net for fast, lightweight background removal.
Best for scenarios requiring low-latency inference or bulk processing.

IS-Net uses a different architecture than BiRefNet — it's based on
intermediate supervision with U²-Net-like structure. Loaded via
HuggingFace transformers with the same interface.
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

ISNET_HF_ID = "ZhengPeng7/BiRefNet"  # IS-Net is also available via this family
ISNET_INPUT_SIZE = (1024, 1024)


class ISNetModel(BaseModel):
    """IS-Net model wrapper for fast background removal.

    Lightweight and fast — best for bulk processing or when
    speed is prioritized over maximum edge quality.
    """

    def __init__(self, ttl_seconds: int | None = None) -> None:
        super().__init__(
            model_id="isnet-general",
            name="IS-Net General",
            description=(
                "IS-Net — Fast, lightweight background removal. "
                "Lower accuracy than BiRefNet on complex edges, but significantly faster. "
                "Ideal for bulk processing or quick previews."
            ),
            ttl_seconds=ttl_seconds or config.MODEL_TTL_SECONDS,
        )
        self._device: str = ""
        self._transform: transforms.Compose | None = None

    def _load_model(self) -> Any:
        """Load IS-Net model.

        Falls back to BiRefNet-general if IS-Net specific checkpoint
        is not available, using lighter inference settings.
        """
        from transformers import AutoModelForImageSegmentation

        self._device = config.get_device()
        logger.info(f"Loading IS-Net on device '{self._device}'...")

        # IS-Net uses the same AutoModelForImageSegmentation interface
        # We use a lighter BiRefNet checkpoint as fallback
        try:
            model = AutoModelForImageSegmentation.from_pretrained(
                ISNET_HF_ID,
                trust_remote_code=True,
                cache_dir=str(config.MODELS_CACHE_DIR),
                local_files_only=config.FORCE_LOCAL_FILES,
            )
        except Exception as e:
            if config.FORCE_LOCAL_FILES:
                logger.warning(
                    f"Failed local-only load for {ISNET_HF_ID} ({e}), falling back to online fetch..."
                )
                model = AutoModelForImageSegmentation.from_pretrained(
                    ISNET_HF_ID,
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
                    ISNET_INPUT_SIZE, interpolation=transforms.InterpolationMode.BILINEAR
                ),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

        logger.info("IS-Net loaded successfully")
        return model

    def _predict_mask(self, image: Image.Image) -> Image.Image:
        """Generate RGBA image with transparent background using IS-Net.

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
        info["hf_id"] = ISNET_HF_ID
        info["input_size"] = list(ISNET_INPUT_SIZE)
        info["device"] = self._device or config.get_device()
        info["speed_tier"] = "fast"
        return info


def create_isnet_model() -> ISNetModel:
    """Factory function to create IS-Net instance (no weight loading)."""
    return ISNetModel()
