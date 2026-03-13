from __future__ import annotations

import asyncio
import io
import numpy as np
import soundfile as sf

from .base import BaseASR, ASRResult, register


@register("elevenlabs")
class ElevenLabsASR(BaseASR):
    """
    ElevenLabs Speech-to-Text (Scribe v2).

    Config (config.yaml):
      asr:
        provider: elevenlabs
        elevenlabs:
          api_key: "your_key"
          model_id: "scribe_v2"
          language_code: "zh"   # 留空则自动检测
    """

    def __init__(self, config: dict):
        self._api_key = config.get("api_key", "")
        self._model_id = config.get("model_id", "scribe_v2")
        self._language_code = config.get("language_code") or None
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

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        client = self._get_client()

        # Convert float32 numpy array → WAV bytes in memory
        buf = io.BytesIO()
        sf.write(buf, audio.astype(np.float32), sample_rate, format="WAV")
        buf.seek(0)
        buf.name = "audio.wav"

        def _call():
            return client.speech_to_text.convert(
                file=buf,
                model_id=self._model_id,
                language_code=self._language_code,
                tag_audio_events=False,
                diarize=False,
            )

        result = await asyncio.get_event_loop().run_in_executor(None, _call)

        text = result.text.strip() if hasattr(result, "text") else str(result).strip()
        language = getattr(result, "language_code", None)

        return ASRResult(text=text, language=language)
