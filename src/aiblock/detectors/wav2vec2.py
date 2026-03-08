"""
Wav2Vec2-based deepfake audio detector.

Uses a fine-tuned wav2vec2 model from HuggingFace.
Default model: Zeyadd-Mostaffa/Deepfake-Audio-Detection-v1
  - ~350 MB, runs on CPU
  - Input: 16 kHz mono audio
  - Output: binary classification (human vs AI/deepfake)

The model is downloaded automatically to ~/.cache/huggingface/ on first use.
"""

import numpy as np

from aiblock.detectors.base import Detector, DetectionResult

_DEFAULT_MODEL = "Zeyadd-Mostaffa/Deepfake-Audio-Detection-v1"


class Wav2Vec2Detector(Detector):
    name = "wav2vec2"

    def __init__(self, model_id: str = _DEFAULT_MODEL, device: str = "cpu"):
        # Lazy import so users without torch/transformers can still use SpectralDetector
        try:
            import torch
            from transformers import AutoFeatureExtractor, AutoModelForAudioClassification
        except ImportError as e:
            raise ImportError(
                "torch and transformers are required for Wav2Vec2Detector. "
                "Install them with: pip install torch transformers"
            ) from e

        self._device = device
        self._extractor = AutoFeatureExtractor.from_pretrained(model_id)
        self._model = AutoModelForAudioClassification.from_pretrained(model_id)
        self._model.to(device)
        self._model.eval()
        self._torch = torch

    def detect(self, audio: np.ndarray, sr: int) -> DetectionResult:
        inputs = self._extractor(
            audio,
            sampling_rate=sr,
            return_tensors="pt",
            padding=True,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with self._torch.no_grad():
            logits = self._model(**inputs).logits

        probs = self._torch.softmax(logits, dim=-1).squeeze().cpu().numpy()

        # Determine which label index corresponds to AI/fake.
        # Models may order labels differently; inspect id2label to find the fake class.
        id2label = self._model.config.id2label
        ai_idx = next(
            (i for i, lbl in id2label.items() if "fake" in lbl.lower() or "ai" in lbl.lower()),
            1,  # fallback: assume index 1 = AI
        )

        score = float(probs[ai_idx])
        confidence = float(abs(score - 0.5) * 2.0)

        return DetectionResult(score=score, confidence=confidence, detector=self.name)
