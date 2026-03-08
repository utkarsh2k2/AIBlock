"""Pipeline integration tests using mocked adapters and synthetic audio."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import soundfile as sf

from aiblock.config import Config, PreprocessConfig, DetectorConfig
from aiblock.detectors.spectral import SpectralDetector
from aiblock.pipeline import Pipeline


def _write_sine_wav(path: Path, sr: int = 16000, duration: float = 25.0):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sf.write(str(path), audio, sr)


def _write_short_wav(path: Path, sr: int = 16000, duration_samples: int = 100):
    sf.write(str(path), np.zeros(duration_samples, dtype=np.float32), sr)


class TestPipeline:
    def setup_method(self):
        self.config = Config(
            preprocess=PreprocessConfig(sample_rate=16000, chunk_sec=10),
            detectors={"spectral": DetectorConfig(weight=1.0)},
            threshold=0.5,
        )

    def test_run_returns_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_file = Path(tmp) / "test.wav"
            _write_sine_wav(audio_file)

            mock_adapter = MagicMock()
            mock_adapter.fetch.return_value = audio_file

            pipeline = Pipeline(
                adapter=mock_adapter,
                detectors=[SpectralDetector()],
                config=self.config,
            )
            result = pipeline.run("https://example.com/fake-url")

        assert result["verdict"] in ("AI", "Human")
        assert 0.0 <= result["score"] <= 1.0
        assert result["chunks"] >= 2  # 25s / 10s = 2 full chunks

    def test_truly_empty_audio_returns_unknown(self):
        """Audio shorter than 0.5s (the minimum chunk floor) → Unknown."""
        with tempfile.TemporaryDirectory() as tmp:
            audio_file = Path(tmp) / "tiny.wav"
            _write_short_wav(audio_file, duration_samples=100)  # 6ms — below 0.5s floor

            mock_adapter = MagicMock()
            mock_adapter.fetch.return_value = audio_file

            pipeline = Pipeline(
                adapter=mock_adapter,
                detectors=[SpectralDetector()],
                config=self.config,
            )
            result = pipeline.run("https://example.com/tiny")

        assert result["verdict"] == "Unknown"

    def test_short_audio_produces_one_chunk(self):
        """9s audio (less than chunk_sec=10) must produce exactly 1 chunk, not Unknown.

        This is the core chunking regression test — the old code dropped short tails.
        """
        with tempfile.TemporaryDirectory() as tmp:
            audio_file = Path(tmp) / "short.wav"
            sr = 16000
            duration_s = 9.0
            sf.write(str(audio_file), np.zeros(int(sr * duration_s), dtype=np.float32), sr)

            mock_adapter = MagicMock()
            mock_adapter.fetch.return_value = audio_file

            pipeline = Pipeline(
                adapter=mock_adapter,
                detectors=[SpectralDetector()],
                config=self.config,
            )
            result = pipeline.run("https://example.com/short")

        assert result["verdict"] in ("AI", "Human"), (
            f"9s audio returned '{result['verdict']}' — chunking fix not applied."
        )
        assert result["chunks"] == 1

    def test_result_schema(self):
        """Result dict always has the expected keys."""
        with tempfile.TemporaryDirectory() as tmp:
            audio_file = Path(tmp) / "test.wav"
            _write_sine_wav(audio_file)

            mock_adapter = MagicMock()
            mock_adapter.fetch.return_value = audio_file

            pipeline = Pipeline(
                adapter=mock_adapter,
                detectors=[SpectralDetector()],
                config=self.config,
            )
            result = pipeline.run("https://example.com/fake-url")

        assert set(result.keys()) >= {"verdict", "score", "confidence", "chunks"}
        assert isinstance(result["score"], float)
        assert isinstance(result["confidence"], float)
        assert isinstance(result["chunks"], int)
