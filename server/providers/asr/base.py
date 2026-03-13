from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np


@dataclass
class ASRResult:
    text: str
    language: str | None = None
    confidence: float | None = None


class BaseASR(ABC):
    """All ASR providers implement this interface."""

    @abstractmethod
    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        """
        Transcribe PCM audio to text.
        audio: float32 numpy array, values in [-1, 1]
        sample_rate: Hz
        """
        ...

    async def close(self) -> None:
        """Optional cleanup."""
        pass


# Registry
_registry: dict[str, type[BaseASR]] = {}


def register(name: str):
    def decorator(cls: type[BaseASR]):
        _registry[name] = cls
        return cls
    return decorator


def get_provider(name: str) -> type[BaseASR]:
    if name not in _registry:
        raise ValueError(f"Unknown ASR provider: {name!r}. Available: {list(_registry)}")
    return _registry[name]
