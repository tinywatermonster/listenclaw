from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class TTSConfig:
    voice: str | None = None
    rate: str = "+0%"
    volume: str = "+0%"
    language: str | None = None


class BaseTTS(ABC):
    """All TTS providers implement this interface."""

    @abstractmethod
    async def synthesize(self, text: str, config: TTSConfig | None = None) -> bytes:
        """Synthesize text to audio bytes (MP3 or WAV)."""
        ...

    async def synthesize_stream(
        self, text: str, config: TTSConfig | None = None
    ) -> AsyncIterator[bytes]:
        """
        Stream audio chunks. Default wraps synthesize().
        Override for providers that support native streaming.
        """
        audio = await self.synthesize(text, config)
        yield audio

    async def close(self) -> None:
        """Optional cleanup."""
        pass


# Registry
_registry: dict[str, type[BaseTTS]] = {}


def register(name: str):
    def decorator(cls: type[BaseTTS]):
        _registry[name] = cls
        return cls
    return decorator


def get_provider(name: str) -> type[BaseTTS]:
    if name not in _registry:
        raise ValueError(f"Unknown TTS provider: {name!r}. Available: {list(_registry)}")
    return _registry[name]
