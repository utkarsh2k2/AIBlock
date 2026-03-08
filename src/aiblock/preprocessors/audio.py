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
    min_chunk = sample_rate // 2  # 0.5 s — prevents silent failures on Shorts / previews

    chunks = []
    for i in range(0, len(audio), chunk_len):
        chunk = audio[i : i + chunk_len]
        if len(chunk) < min_chunk:
            continue
        if len(chunk) < chunk_len:
            chunk = np.pad(chunk, (0, chunk_len - len(chunk)))  # zero-pad short tail
        chunks.append(chunk)

    return chunks, sample_rate
