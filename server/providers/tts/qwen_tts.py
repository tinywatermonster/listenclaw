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
        from qwen_tts import QwenTTSPipeline
        self._pipeline = QwenTTSPipeline(self._model_id)
        logger.info("Qwen3-TTS model loaded")

    async def synthesize(self, text: str, config: TTSConfig | None = None) -> bytes:
        chunks = []
        async for chunk in self.synthesize_stream(text, config):
            chunks.append(chunk)
        return b"".join(chunks)

    async def synthesize_stream(
        self, text: str, config: TTSConfig | None = None
    ) -> AsyncIterator[bytes]:
        import asyncio
        self._load()

        voice = (config and config.voice) or self._voice
        logger.info("Qwen3-TTS synthesizing: %r (voice=%s)", text[:40], voice)

        def _run():
            import tempfile, os
            # qwen-tts writes to a file; we read it back as bytes
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                out_path = f.name
            try:
                kwargs = {"text": text, "output_path": out_path}
                if voice:
                    kwargs["voice"] = voice
                self._pipeline.generate(**kwargs)
                with open(out_path, "rb") as f:
                    return f.read()
            finally:
                os.unlink(out_path)

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
