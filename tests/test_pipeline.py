"""Pipeline integration test using mocked adapter and a synthetic audio file."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_empty_audio_returns_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_file = Path(tmp) / "short.wav"
            # Write sub-1s audio (will be dropped by preprocessor)
            sf.write(str(audio_file), np.zeros(100, dtype=np.float32), 16000)

            mock_adapter = MagicMock()
            mock_adapter.fetch.return_value = audio_file

            pipeline = Pipeline(
                adapter=mock_adapter,
                detectors=[SpectralDetector()],
                config=self.config,
            )
            result = pipeline.run("https://example.com/short")

        assert result["verdict"] == "Unknown"
