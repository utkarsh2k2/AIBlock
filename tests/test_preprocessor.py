"""Tests for the audio preprocessor chunking fix."""

import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from aiblock.preprocessors.audio import preprocess


def _write_wav(path: Path, samples: int, sr: int = 16000):
    sf.write(str(path), np.zeros(samples, dtype=np.float32), sr)


class TestPreprocess:
    SR = 16000
    CHUNK_SEC = 10

    def test_long_audio_multiple_chunks(self):
        """25s audio → 2 full chunks + 1 padded tail = 3 chunks."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(Path(f.name), self.SR * 25)
            chunks, sr = preprocess(Path(f.name), sample_rate=self.SR, chunk_sec=self.CHUNK_SEC)

        assert len(chunks) == 3  # 10s + 10s + 5s (padded to 10s)
        assert sr == self.SR
        for chunk in chunks:
            assert len(chunk) == self.SR * self.CHUNK_SEC, "All chunks must be exactly chunk_len"

    def test_short_audio_one_chunk(self):
        """9s audio (< chunk_sec) → 1 zero-padded chunk, not 0 chunks."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(Path(f.name), int(self.SR * 9))
            chunks, sr = preprocess(Path(f.name), sample_rate=self.SR, chunk_sec=self.CHUNK_SEC)

        assert len(chunks) == 1, f"Expected 1 chunk for 9s audio, got {len(chunks)}"
        assert len(chunks[0]) == self.SR * self.CHUNK_SEC  # padded

    def test_exactly_one_chunk_length(self):
        """Exactly 10s audio → 1 chunk, no padding needed."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(Path(f.name), self.SR * 10)
            chunks, _ = preprocess(Path(f.name), sample_rate=self.SR, chunk_sec=self.CHUNK_SEC)

        assert len(chunks) == 1

    def test_sub_half_second_dropped(self):
        """Audio shorter than 0.5s (below min_chunk floor) → 0 chunks."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(Path(f.name), 100)  # 6ms
            chunks, _ = preprocess(Path(f.name), sample_rate=self.SR, chunk_sec=self.CHUNK_SEC)

        assert len(chunks) == 0

    def test_half_second_included(self):
        """Audio of exactly 0.5s (min_chunk floor) → 1 chunk."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            _write_wav(Path(f.name), self.SR // 2)  # 8000 samples = 0.5s
            chunks, _ = preprocess(Path(f.name), sample_rate=self.SR, chunk_sec=self.CHUNK_SEC)

        assert len(chunks) == 1
        assert len(chunks[0]) == self.SR * self.CHUNK_SEC  # padded

    def test_tail_chunk_zero_padded(self):
        """Partial tail chunk is zero-padded to chunk_len, not truncated."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tail_samples = self.SR * 3  # 3s tail after 10s chunk
            _write_wav(Path(f.name), self.SR * 10 + tail_samples)
            chunks, _ = preprocess(Path(f.name), sample_rate=self.SR, chunk_sec=self.CHUNK_SEC)

        assert len(chunks) == 2
        # Tail chunk is padded to full chunk length
        assert len(chunks[1]) == self.SR * self.CHUNK_SEC
        # Padded region is zeros
        assert np.all(chunks[1][tail_samples:] == 0.0)
