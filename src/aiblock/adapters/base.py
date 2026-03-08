from abc import ABC, abstractmethod
from pathlib import Path


class PlatformAdapter(ABC):
    """Abstract base for all platform adapters.

    Each adapter is responsible for fetching audio from a single platform
    and returning the path to a local audio file (mp3/wav/flac).

    To add a new platform, subclass this and implement `fetch`.
    Register it in `pipeline.py`'s ADAPTER_REGISTRY.
    """

    @abstractmethod
    def fetch(self, url: str, output_dir: Path) -> Path:
        """Download audio from `url`, save under `output_dir`, return file path."""
