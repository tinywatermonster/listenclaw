"""
Wake word detector.

Config (in config.yaml under session.wake_word):
  enabled: false          # set true to require wake word before listening
  engine: openwakeword    # openwakeword | keyword (simple keyword match on ASR)
  model: hey_jarvis       # openwakeword model name
  threshold: 0.5          # detection confidence threshold

When disabled: every audio frame goes straight to VAD/listening.
When enabled: audio passes through the wake detector first;
  on detection the engine fires on_wake() and opens a listening window.

openwakeword runs on raw 16kHz int16 PCM — same format as the audio engine.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Awaitable

import numpy as np

logger = logging.getLogger(__name__)

WakeCallback = Callable[[], Awaitable[None]]


@dataclass
class WakeConfig:
    enabled: bool = False
    engine: str = "openwakeword"   # openwakeword | keyword
    model: str = "hey_jarvis"
    threshold: float = 0.5
    keyword: str = ""              # for engine=keyword, matched against ASR text


class WakeDetector:
    """
    Wraps wake word detection.
    Call process_frame() on every VAD frame.
    Fires on_wake callback when wake word is detected.
    """

    def __init__(self, config: WakeConfig, on_wake: WakeCallback):
        self._cfg = config
        self._on_wake = on_wake
        self._oww = None
        self._cooldown = False  # prevent re-triggering immediately

        if config.enabled and config.engine == "openwakeword":
            self._load_oww()

    def _load_oww(self):
        try:
            from openwakeword.model import Model
            self._oww = Model(
                wakeword_models=[self._cfg.model],
                inference_framework="onnx",
            )
            logger.info("Wake word loaded: %s (threshold=%.2f)", self._cfg.model, self._cfg.threshold)
        except ImportError:
            logger.warning(
                "openwakeword not installed — wake word disabled. "
                "Run: pip install openwakeword"
            )
            self._cfg.enabled = False
        except Exception as e:
            logger.warning("Failed to load wake word model %r: %s", self._cfg.model, e)
            self._cfg.enabled = False

    async def process_frame(self, pcm_int16: bytes):
        """Call with each 80ms chunk (1280 samples at 16kHz) of int16 PCM."""
        if not self._cfg.enabled or self._oww is None or self._cooldown:
            return

        audio = np.frombuffer(pcm_int16, dtype=np.int16)
        predictions = self._oww.predict(audio)

        for model_name, score in predictions.items():
            if score >= self._cfg.threshold:
                logger.info("Wake word detected: %s (score=%.3f)", model_name, score)
                self._cooldown = True
                asyncio.create_task(self._reset_cooldown())
                await self._on_wake()
                break

    async def _reset_cooldown(self, delay: float = 3.0):
        await asyncio.sleep(delay)
        self._cooldown = False

    async def check_text(self, text: str) -> bool:
        """
        For engine=keyword: check if wake keyword appears in ASR text.
        Returns True if wake word matched.
        """
        if not self._cfg.enabled or self._cfg.engine != "keyword":
            return False
        kw = self._cfg.keyword.lower()
        return bool(kw and kw in text.lower())


def from_config(cfg: dict, on_wake: WakeCallback) -> WakeDetector:
    wake_cfg_raw = cfg.get("session", {}).get("wake_word", {}) or {}
    wake_cfg = WakeConfig(
        enabled=wake_cfg_raw.get("enabled", False),
        engine=wake_cfg_raw.get("engine", "openwakeword"),
        model=wake_cfg_raw.get("model", "hey_jarvis"),
        threshold=float(wake_cfg_raw.get("threshold", 0.5)),
        keyword=wake_cfg_raw.get("keyword", ""),
    )
    return WakeDetector(wake_cfg, on_wake)
