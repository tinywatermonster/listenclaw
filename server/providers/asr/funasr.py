import logging
import numpy as np
from .base import BaseASR, ASRResult, register

logger = logging.getLogger(__name__)


@register("funasr")
class FunASR(BaseASR):
    """
    SenseVoice-Small via FunASR — 15x faster than Whisper-Large on Chinese.
    pip install funasr modelscope
    Model auto-downloads on first use (~200MB).
    """

    def __init__(self, config: dict):
        self._model_name = config.get("model", "iic/SenseVoiceSmall")
        self._language = config.get("language", "zh")
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        logger.info("Loading FunASR model: %s", self._model_name)
        from funasr import AutoModel
        self._model = AutoModel(
            model=self._model_name,
            trust_remote_code=True,
            disable_update=True,
        )
        logger.info("FunASR model loaded")

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        import asyncio
        self._load()

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            import librosa
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

        audio = audio.astype(np.float32)

        def _run():
            res = self._model.generate(
                input=audio,
                cache={},
                language=self._language,
                use_itn=True,
                batch_size_s=60,
            )
            if res and len(res) > 0:
                return res[0].get("text", "").strip()
            return ""

        text = await asyncio.get_event_loop().run_in_executor(None, _run)
        # SenseVoice prepends emotion/event tags like <|zh|><|NEUTRAL|><|Speech|><|woitn|>
        # Strip them
        import re
        text = re.sub(r"<\|[^|]+\|>", "", text).strip()

        logger.info("FunASR result: %r", text)
        return ASRResult(text=text, language=self._language)
