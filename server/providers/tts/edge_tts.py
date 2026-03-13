import io
from typing import AsyncIterator
from .base import BaseTTS, TTSConfig, register


@register("edge_tts")
class EdgeTTS(BaseTTS):
    """
    Microsoft Edge TTS — free, no API key needed.
    Uses the edge-tts Python package (reverse-engineered Edge browser TTS).
    """

    def __init__(self, config: dict):
        self._default_voice = config.get("voice", "zh-CN-XiaoxiaoNeural")
        self._default_rate = config.get("rate", "+0%")
        self._default_volume = config.get("volume", "+0%")

    async def synthesize(self, text: str, config: TTSConfig | None = None) -> bytes:
        chunks = []
        async for chunk in self.synthesize_stream(text, config):
            chunks.append(chunk)
        return b"".join(chunks)

    async def synthesize_stream(
        self, text: str, config: TTSConfig | None = None
    ) -> AsyncIterator[bytes]:
        import edge_tts

        voice = (config and config.voice) or self._default_voice
        rate = (config and config.rate) or self._default_rate
        volume = (config and config.volume) or self._default_volume

        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
