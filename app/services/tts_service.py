from __future__ import annotations

import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

import soundfile as sf
import torch

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.enabled = self.settings.sbv2_enabled
        self.model: Any | None = None
        self.languages: Any | None = None
        self.default_style: str = "Neutral"
        self.default_style_weight: float = 1.0
        self._startup_error: str | None = None

    def _resolve_device(self) -> str:
        configured = (self.settings.sbv2_device or "").strip().lower()
        if configured in {"cpu", "mps"}:
            if configured == "mps" and not torch.backends.mps.is_available():
                logger.warning(
                    "SBV2 configured for MPS but unavailable, falling back to CPU"
                )
                return "cpu"
            return configured
        return "mps" if torch.backends.mps.is_available() else "cpu"

    async def startup(self) -> None:
        if not self.enabled:
            logger.info("SBV2 disabled via SBV2_ENABLED=false")
            return

        try:
            from style_bert_vits2.constants import (
                DEFAULT_STYLE,
                DEFAULT_STYLE_WEIGHT,
                Languages,
            )
            from style_bert_vits2.nlp import bert_models
            from style_bert_vits2.tts_model import TTSModel

            self.languages = Languages
            self.default_style = DEFAULT_STYLE
            self.default_style_weight = DEFAULT_STYLE_WEIGHT

            # Preload BERT tokenizers/models once for predictable first-request latency.
            bert_models.load_model(Languages.EN)

            model_dir = (
                Path(self.settings.sbv2_assets_root) / self.settings.sbv2_model_name
            )
            model_path = model_dir / "model.safetensors"
            config_path = model_dir / "config.json"
            style_vec_path = model_dir / "style_vectors.npy"

            missing = [
                str(path)
                for path in (model_path, config_path, style_vec_path)
                if not path.exists()
            ]
            if missing:
                raise FileNotFoundError(
                    "Missing SBV2 model files: " + ", ".join(missing)
                )

            device = self._resolve_device()
            self.model = TTSModel(
                model_path=model_path,
                config_path=config_path,
                style_vec_path=style_vec_path,
                device=device,
            )
            logger.info(
                "Style-BERT-VITS2 loaded on %s with model %s (default language: %s)",
                device.upper(),
                self.settings.sbv2_model_name,
                self.settings.sbv2_default_language,
            )
        except Exception as exc:  # pragma: no cover - depends on local model/runtime
            self.model = None
            self._startup_error = str(exc)
            logger.exception("Failed to initialize SBV2 TTS service")

    async def shutdown(self) -> None:
        self.model = None

    @lru_cache(maxsize=50)
    def synthesize(
        self,
        text: str,
        emotion: str = "talking",
        speed: float = 0.95,
        style_weight: float = 1.0,
    ) -> bytes:
        if not self.enabled:
            raise RuntimeError("SBV2 disabled")
        if self.model is None or self.languages is None:
            reason = self._startup_error or "SBV2 is not initialized"
            raise RuntimeError(reason)

        clean_text = text.strip()
        if not clean_text:
            raise ValueError("text cannot be blank")

        style_map: dict[str, tuple[str, float]] = {
            "happy": ("Happy", 1.35),
            "sad": ("Sad", 0.85),
            "angry": ("Angry", 1.45),
            "surprised": ("Surprised", 1.25),
            "thinking": ("Neutral", 0.65),
            "talking": ("Neutral", 1.05),
            "idle": ("Neutral", 0.9),
        }
        style_name, extra_weight = style_map.get(
            emotion.lower(), (self.default_style, self.default_style_weight)
        )
        final_weight = min(1.85, max(0.1, style_weight * extra_weight))
        final_speed = min(1.6, max(0.6, speed))

        try:
            sample_rate, audio = self.model.infer(
                text=clean_text,
                speaker_id=self.settings.sbv2_speaker_id,
                style=style_name,
                style_weight=final_weight,
                length=final_speed,
                language=self.languages.EN,
                sdp_ratio=0.25,
                noise=0.25,
                noise_w=0.4,
                line_split=True,
                split_interval=0.3,
            )
        except Exception:
            # Some custom checkpoints expose fewer styles; fall back gracefully.
            sample_rate, audio = self.model.infer(
                text=clean_text,
                speaker_id=self.settings.sbv2_speaker_id,
                style=self.default_style,
                style_weight=min(1.5, max(0.1, style_weight)),
                length=final_speed,
                language=self.languages.EN,
                sdp_ratio=0.25,
                noise=0.25,
                noise_w=0.4,
                line_split=True,
                split_interval=0.3,
            )

        buffer = BytesIO()
        sf.write(buffer, audio, sample_rate, format="WAV")
        buffer.seek(0)
        return buffer.read()


tts_service = TTSService()
