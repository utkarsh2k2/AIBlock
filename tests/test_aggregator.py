"""Tests for the aggregator."""

import pytest

from aiblock.aggregator import aggregate
from aiblock.detectors.base import DetectionResult


def _result(score: float, detector: str = "spectral") -> DetectionResult:
    return DetectionResult(score=score, confidence=abs(score - 0.5) * 2, detector=detector)


class TestAggregate:
    def test_empty_returns_unknown(self):
        out = aggregate([], {})
        assert out["verdict"] == "Unknown"

    def test_high_score_is_ai(self):
        results = [[_result(0.9)]]
        out = aggregate(results, {"spectral": 1.0}, threshold=0.5)
        assert out["verdict"] == "AI"
        assert out["score"] == pytest.approx(0.9)

    def test_low_score_is_human(self):
        results = [[_result(0.1)]]
        out = aggregate(results, {"spectral": 1.0}, threshold=0.5)
        assert out["verdict"] == "Human"

    def test_median_over_chunks(self):
        # Outlier chunk (0.9) should not dominate when median of [0.1, 0.2, 0.9] = 0.2
        results = [[_result(0.1)], [_result(0.2)], [_result(0.9)]]
        out = aggregate(results, {"spectral": 1.0}, threshold=0.5)
        assert out["verdict"] == "Human"
        assert out["score"] == pytest.approx(0.2)

    def test_weighted_average_per_chunk(self):
        chunk = [_result(0.8, "wav2vec2"), _result(0.2, "spectral")]
        weights = {"wav2vec2": 3.0, "spectral": 1.0}
        # Expected weighted avg = (0.8*3 + 0.2*1) / 4 = 0.65
        out = aggregate([chunk], weights, threshold=0.5)
        assert out["verdict"] == "AI"
        assert out["score"] == pytest.approx(0.65)

    def test_chunks_count(self):
        results = [[_result(0.5)]] * 5
        out = aggregate(results, {"spectral": 1.0})
        assert out["chunks"] == 5
