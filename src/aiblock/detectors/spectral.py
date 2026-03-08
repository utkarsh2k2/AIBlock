"""
Spectral heuristic detector.

AI-generated audio tends to exhibit:
  - Abnormally high spectral flatness (less tonal variation)
  - Lower MFCC variance (over-smooth timbre)
  - Unusually consistent zero-crossing rate

These features are combined into a heuristic score. No model download required.
Serves as a fast pre-filter and calibration signal alongside the wav2vec2 detector.
"""

import librosa
import numpy as np

from aiblock.detectors.base import Detector, DetectionResult


# Empirical thresholds derived from published AI-audio analysis literature.
# Tune these if you accumulate labelled examples.
_FLATNESS_AI_THRESHOLD = 0.15   # mean spectral flatness; AI audio typically > 0.10
_MFCC_VAR_HUMAN_MIN = 30.0      # mean MFCC variance; human speech typically > 30


def _spectral_score(audio: np.ndarray, sr: int) -> tuple[float, float]:
    """Return (ai_score, confidence) in [0, 1]."""
    flatness = librosa.feature.spectral_flatness(y=audio)
    mean_flatness = float(np.mean(flatness))

    mfccs = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13)
    mfcc_var = float(np.mean(np.var(mfccs, axis=1)))

    zcr = librosa.feature.zero_crossing_rate(audio)
    zcr_std = float(np.std(zcr))

    # Each sub-signal contributes 0–1 toward AI likelihood
    flatness_signal = min(mean_flatness / _FLATNESS_AI_THRESHOLD, 1.0)
    mfcc_signal = max(0.0, 1.0 - mfcc_var / _MFCC_VAR_HUMAN_MIN)
    zcr_signal = max(0.0, 1.0 - zcr_std / 0.05)  # low zcr_std → more AI-like

    score = (flatness_signal + mfcc_signal + zcr_signal) / 3.0

    # Confidence: how far from the 0.5 boundary (max = 1.0)
    confidence = abs(score - 0.5) * 2.0

    return score, confidence


class SpectralDetector(Detector):
    name = "spectral"

    def detect(self, audio: np.ndarray, sr: int) -> DetectionResult:
        score, confidence = _spectral_score(audio, sr)
        return DetectionResult(score=score, confidence=confidence, detector=self.name)
