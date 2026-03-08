"""Tests for detectors — no internet or model download required."""

import numpy as np
import pytest

from aiblock.detectors.base import DetectionResult
from aiblock.detectors.spectral import SpectralDetector


def _sine_wave(freq: float = 440.0, sr: int = 16000, duration: float = 10.0) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _white_noise(sr: int = 16000, duration: float = 10.0) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.standard_normal(int(sr * duration)).astype(np.float32)


class TestSpectralDetector:
    def setup_method(self):
        self.detector = SpectralDetector()

    def test_returns_detection_result(self):
        audio = _sine_wave()
        result = self.detector.detect(audio, sr=16000)
        assert isinstance(result, DetectionResult)
        assert result.detector == "spectral"

    def test_score_in_range(self):
        for audio in [_sine_wave(), _white_noise()]:
            result = self.detector.detect(audio, sr=16000)
            assert 0.0 <= result.score <= 1.0
            assert 0.0 <= result.confidence <= 1.0

    def test_noise_scores_higher_than_sine(self):
        """White noise has HIGH spectral flatness (all frequencies equal power).
        A pure sine has LOW spectral flatness (power concentrated at one frequency).
        The spectral heuristic uses flatness as an AI signal, so noise should score higher.
        """
        sine_result = self.detector.detect(_sine_wave(), sr=16000)
        noise_result = self.detector.detect(_white_noise(), sr=16000)
        assert noise_result.score > sine_result.score
