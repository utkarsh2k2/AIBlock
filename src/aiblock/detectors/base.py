from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class DetectionResult:
    score: float      # 0.0 = human, 1.0 = AI
    confidence: float # certainty of the prediction
    detector: str     # name for audit trail


class Detector(ABC):
    name: str

    @abstractmethod
    def detect(self, audio: np.ndarray, sr: int) -> DetectionResult:
        """Return a DetectionResult for a single audio chunk."""
