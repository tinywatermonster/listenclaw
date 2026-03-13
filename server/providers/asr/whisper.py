import numpy as np
from .base import BaseASR, ASRResult, register


@register("whisper")
class WhisperASR(BaseASR):
    """
    Local ASR using faster-whisper.
    Lazy-loads model on first use to avoid startup delay.
    """

    def __init__(self, config: dict):
        self._model_size = config.get("model", "base")
        self._language = config.get("language") or None  # None = auto-detect
        self._device = config.get("device", "cpu")
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type="int8",
            )

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        self._load()

        # faster-whisper expects float32 at 16kHz
        if sample_rate != 16000:
            import librosa
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

        audio = audio.astype(np.float32)

        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,
        )
        text = "".join(seg.text for seg in segments).strip()
        return ASRResult(
            text=text,
            language=info.language,
            confidence=info.language_probability,
        )
