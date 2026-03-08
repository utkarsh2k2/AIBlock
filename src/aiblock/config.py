"""Config loading from YAML into typed dataclasses."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class PreprocessConfig:
    sample_rate: int = 16000
    chunk_sec: int = 10


@dataclass
class DetectorConfig:
    weight: float = 1.0
    model_id: str = "Zeyadd-Mostaffa/Deepfake-Audio-Detection-v1"
    device: str = "cpu"


@dataclass
class Config:
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    detectors: dict[str, DetectorConfig] = field(default_factory=dict)
    threshold: float = 0.5

    @classmethod
    def from_yaml(cls, path: Path) -> "Config":
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        preprocess = PreprocessConfig(**raw.get("preprocess", {}))
        threshold = float(raw.get("threshold", 0.5))

        detectors = {}
        for name, vals in raw.get("detectors", {}).items():
            detectors[name] = DetectorConfig(**{k: v for k, v in vals.items()})

        return cls(preprocess=preprocess, detectors=detectors, threshold=threshold)

    def weights(self) -> dict[str, float]:
        return {name: cfg.weight for name, cfg in self.detectors.items()}
