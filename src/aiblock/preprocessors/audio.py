from pathlib import Path

import librosa
import numpy as np


def preprocess(
    path: Path,
    sample_rate: int = 16000,
    chunk_sec: int = 10,
) -> tuple[list[np.ndarray], int]:
    """
    Load audio file, resample to mono at `sample_rate`, split into chunks.

    Returns:
        (chunks, sample_rate) — each chunk is a 1-D float32 numpy array
    """
    audio, _ = librosa.load(str(path), sr=sample_rate, mono=True)

    chunk_len = sample_rate * chunk_sec
    chunks = [
        audio[i : i + chunk_len]
        for i in range(0, len(audio), chunk_len)
        if len(audio[i : i + chunk_len]) >= sample_rate  # drop sub-1s tail
    ]

    return chunks, sample_rate
