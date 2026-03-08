"""Pipeline: orchestrates adapter → preprocess → detect → aggregate."""

import tempfile
from pathlib import Path

from aiblock.adapters.base import PlatformAdapter
from aiblock.adapters.youtube import YouTubeAdapter
from aiblock.adapters.spotify import SpotifyAdapter
from aiblock.aggregator import aggregate
from aiblock.config import Config
from aiblock.detectors.base import Detector
from aiblock.detectors.spectral import SpectralDetector
from aiblock.preprocessors.audio import preprocess

ADAPTER_REGISTRY: dict[str, type[PlatformAdapter]] = {
    "youtube": YouTubeAdapter,
    "spotify": SpotifyAdapter,
}

DETECTOR_REGISTRY: dict[str, type[Detector]] = {
    "spectral": SpectralDetector,
    # wav2vec2 registered lazily to avoid mandatory torch import
}


def _build_detectors(config: Config) -> list[Detector]:
    detectors = []
    for name, cfg in config.detectors.items():
        if name == "wav2vec2":
            from aiblock.detectors.wav2vec2 import Wav2Vec2Detector
            detectors.append(Wav2Vec2Detector(model_id=cfg.model_id, device=cfg.device))
        elif name in DETECTOR_REGISTRY:
            detectors.append(DETECTOR_REGISTRY[name]())
        else:
            raise ValueError(f"Unknown detector: {name!r}")
    return detectors


class Pipeline:
    def __init__(self, adapter: PlatformAdapter, detectors: list[Detector], config: Config):
        self.adapter = adapter
        self.detectors = detectors
        self.config = config

    def run(self, url: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="aiblock_") as tmp:
            audio_path = self.adapter.fetch(url, Path(tmp))
            chunks, sr = preprocess(
                audio_path,
                sample_rate=self.config.preprocess.sample_rate,
                chunk_sec=self.config.preprocess.chunk_sec,
            )

        if not chunks:
            return {"verdict": "Unknown", "score": 0.0, "confidence": 0.0, "chunks": 0}

        results = [
            [detector.detect(chunk, sr) for detector in self.detectors]
            for chunk in chunks
        ]

        return aggregate(results, self.config.weights(), self.config.threshold)


def build_pipeline(platform: str, config: Config) -> Pipeline:
    if platform not in ADAPTER_REGISTRY:
        raise ValueError(
            f"Unknown platform: {platform!r}. "
            f"Available: {list(ADAPTER_REGISTRY)}"
        )
    adapter = ADAPTER_REGISTRY[platform]()
    detectors = _build_detectors(config)
    return Pipeline(adapter=adapter, detectors=detectors, config=config)
