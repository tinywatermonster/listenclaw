from __future__ import annotations

from typing import AsyncIterator
from .base import BaseTTS, TTSConfig, register


@register("elevenlabs")
class ElevenLabsTTS(BaseTTS):
    """
    ElevenLabs TTS — high quality, supports streaming.

    Config (config.yaml):
      tts:
        provider: elevenlabs
        elevenlabs:
          api_key: "your_key"
          voice_id: "JBFqnCBsd6RMkjVDRZzb"   # default: George
          model_id: "eleven_multilingual_v2"
          stability: 0.5
          similarity_boost: 0.75
          stream_chunk_size: 1024

    Get voice IDs from: https://elevenlabs.io/voice-library
    """

    def __init__(self, config: dict):
        self._api_key = config.get("api_key", "")
        self._voice_id = config.get("voice_id", "JBFqnCBsd6RMkjVDRZzb")
        self._model_id = config.get("model_id", "eleven_multilingual_v2")
        self._stability = float(config.get("stability", 0.5))
        self._similarity_boost = float(config.get("similarity_boost", 0.75))
        self._chunk_size = int(config.get("stream_chunk_size", 1024))
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from elevenlabs.client import ElevenLabs
            except ImportError:
                raise RuntimeError(
                    "elevenlabs not installed. Run: pip install elevenlabs"
                )
            self._client = ElevenLabs(api_key=self._api_key)
        return self._client

    async def synthesize(self, text: str, config: TTSConfig | None = None) -> bytes:
        chunks = []
        async for chunk in self.synthesize_stream(text, config):
            chunks.append(chunk)
        return b"".join(chunks)

    async def synthesize_stream(
        self, text: str, config: TTSConfig | None = None
    ) -> AsyncIterator[bytes]:
        import asyncio

        client = self._get_client()
        voice_id = (config and config.voice) or self._voice_id

        voice_settings = {
            "stability": self._stability,
            "similarity_boost": self._similarity_boost,
        }

        # ElevenLabs SDK is sync — run in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()

        def _stream():
            return client.text_to_speech.convert_as_stream(
                voice_id=voice_id,
                text=text,
                model_id=self._model_id,
                voice_settings=voice_settings,
            )

        audio_stream = await loop.run_in_executor(None, _stream)

        for chunk in audio_stream:
            if chunk:
                yield chunk
