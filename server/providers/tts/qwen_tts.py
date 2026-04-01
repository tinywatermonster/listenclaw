import io
import logging
from typing import AsyncIterator
from .base import BaseTTS, TTSConfig, register

logger = logging.getLogger(__name__)


@register("qwen_tts")
class QwenTTS(BaseTTS):
    """
    Qwen3-TTS — Alibaba open-source TTS, very natural Chinese voice.
    pip install qwen-tts
    Model: Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice (auto-downloads, ~3.5GB)
    Runs on Apple Silicon MPS.
    """

    def __init__(self, config: dict):
        self._model_id = config.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
        self._voice = config.get("voice", None)  # None = model default
        self._pipeline = None

    def _load(self):
        if self._pipeline is not None:
            return
        logger.info("Loading Qwen3-TTS model: %s", self._model_id)
        from qwen_tts import Qwen3TTSModel
        self._pipeline = Qwen3TTSModel.from_pretrained(self._model_id)
        speakers = self._pipeline.get_supported_speakers()
        logger.info("Qwen3-TTS model loaded, speakers: %s", speakers[:5])
        # Warm up: run a silent inference so code_predictor initializes once
        voice = self._voice or "Chelsie"
        if voice.lower() not in [s.lower() for s in speakers]:
            voice = speakers[0]
        try:
            self._pipeline.generate_custom_voice(text="嗯", speaker=voice, language="chinese")
            logger.info("Qwen3-TTS warm-up done")
        except Exception as e:
            logger.warning("Qwen3-TTS warm-up failed (non-fatal): %s", e)

    async def synthesize(self, text: str, config: TTSConfig | None = None) -> bytes:
        chunks = []
        async for chunk in self.synthesize_stream(text, config):
            chunks.append(chunk)
        return b"".join(chunks)

    async def synthesize_stream(
        self, text: str, config: TTSConfig | None = None
    ) -> AsyncIterator[bytes]:
        import asyncio
        import io
        import numpy as np
        import scipy.io.wavfile
        self._load()

        voice = (config and config.voice) or self._voice or "Chelsie"
        logger.info("Qwen3-TTS synthesizing: %r (speaker=%s)", text[:40], voice)

        def _run():
            arrays, sample_rate = self._pipeline.generate_custom_voice(
                text=text,
                speaker=voice,
                language="chinese",
            )
            audio = arrays[0]  # np.ndarray float32
            # Convert to int16 WAV in memory
            buf = io.BytesIO()
            scipy.io.wavfile.write(buf, sample_rate, (audio * 32767).astype(np.int16))
            return buf.getvalue()

        wav_bytes = await asyncio.get_event_loop().run_in_executor(None, _run)

        # Convert WAV → MP3 so frontend can play it
        try:
            import subprocess
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-i", "pipe:0", "-f", "mp3", "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            mp3_bytes, _ = await proc.communicate(input=wav_bytes)
            logger.info("Qwen3-TTS done: %d bytes MP3", len(mp3_bytes))
            yield mp3_bytes
        except Exception:
            # ffmpeg not available — yield raw WAV (browser can play WAV too)
            logger.warning("ffmpeg not found, yielding raw WAV")
            yield wav_bytes
