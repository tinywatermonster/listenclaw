"""
Audio engine + session state machine.

State transitions:
  IDLE ──► WAKE ──► LISTENING ──► PROCESSING ──► SPEAKING ──► IDLE
  (wake word         ▲                                │
   optional)         └──── FOLLOW_UP ◄───────────────┘

Audio frames come in via push_audio().
The engine uses webrtcvad to detect speech start/end,
then fires events to a registered callback.

Barge-in: VAD keeps running during SPEAKING. If BARGE_IN_FRAMES consecutive
speech frames are detected, the engine fires "interrupted" and returns to
LISTENING — the session layer is responsible for cancelling the TTS stream.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable

import numpy as np
import webrtcvad

logger = logging.getLogger(__name__)

# Consecutive speech frames required to trigger barge-in (~150ms at 30ms/frame)
BARGE_IN_FRAMES = 5


class State(str, Enum):
    IDLE = "idle"
    WAKE = "wake"           # wake-word detected, waiting for speech
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    FOLLOW_UP = "follow_up"


@dataclass
class AudioEngineConfig:
    sample_rate: int = 16000
    chunk_ms: int = 30            # VAD frame length: 10 / 20 / 30
    vad_aggressiveness: int = 2   # 0-3
    silence_frames: int = 20      # frames of silence → end-of-speech (~600ms at 30ms)
    follow_up_timeout: float = 8.0
    barge_in_frames: int = BARGE_IN_FRAMES


# ── Event types ────────────────────────────────────────────────────────────────

@dataclass
class Event:
    type: str
    data: dict = field(default_factory=dict)


EventCallback = Callable[[Event], Awaitable[None]]


# ── AudioEngine ────────────────────────────────────────────────────────────────

class AudioEngine:
    """
    Core audio loop.
    Push raw PCM frames in → get state change events out via callback.
    """

    def __init__(self, config: AudioEngineConfig, callback: EventCallback):
        self._cfg = config
        self._cb = callback
        self._vad = webrtcvad.Vad(config.vad_aggressiveness)
        self._frame_bytes = int(config.sample_rate * config.chunk_ms / 1000) * 2  # int16
        self._state = State.IDLE
        self._speech_buf: list[bytes] = []
        self._silence_count = 0
        self._speech_detected = False
        self._barge_in_count = 0           # consecutive speech frames during SPEAKING
        self._follow_up_task: asyncio.Task | None = None
        self._buffer: deque = deque()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        return self._state

    async def _emit(self, event_type: str, **data):
        await self._cb(Event(type=event_type, data=data))

    async def _set_state(self, new_state: State):
        if self._state != new_state:
            self._state = new_state
            await self._emit("state_change", state=new_state.value)

    async def push_audio(self, pcm_int16: bytes):
        """Feed raw PCM bytes (int16, mono, configured sample_rate)."""
        async with self._lock:
            self._buffer.append(pcm_int16)
            combined = b"".join(self._buffer)
            self._buffer.clear()

            while len(combined) >= self._frame_bytes:
                frame = combined[: self._frame_bytes]
                combined = combined[self._frame_bytes:]
                await self._process_vad_frame(frame)

            if combined:
                self._buffer.append(combined)

    async def _process_vad_frame(self, frame: bytes):
        # Skip VAD entirely only while ASR/Agent is running (PROCESSING)
        if self._state == State.PROCESSING:
            return

        is_speech = self._vad.is_speech(frame, self._cfg.sample_rate)

        # ── Barge-in detection during SPEAKING ────────────────────────────
        if self._state == State.SPEAKING:
            if is_speech:
                self._barge_in_count += 1
                if self._barge_in_count >= self._cfg.barge_in_frames:
                    self._barge_in_count = 0
                    self._speech_buf.clear()
                    self._silence_count = 0
                    self._speech_detected = False
                    self._cancel_follow_up()
                    await self._set_state(State.LISTENING)
                    await self._emit("interrupted")
                    logger.debug("Barge-in detected")
            else:
                self._barge_in_count = max(0, self._barge_in_count - 1)
            return

        # ── Normal speech detection (IDLE / WAKE / LISTENING / FOLLOW_UP) ─
        if is_speech:
            self._silence_count = 0
            if not self._speech_detected:
                self._speech_detected = True
                self._cancel_follow_up()
                await self._set_state(State.LISTENING)
                logger.debug("Speech start")
            self._speech_buf.append(frame)

        else:
            if self._speech_detected:
                self._silence_count += 1
                self._speech_buf.append(frame)  # keep trailing silence for context

                if self._silence_count >= self._cfg.silence_frames:
                    audio_bytes = b"".join(self._speech_buf)
                    self._speech_buf.clear()
                    self._silence_count = 0
                    self._speech_detected = False
                    logger.debug("Speech end, %d bytes", len(audio_bytes))
                    await self._set_state(State.PROCESSING)
                    await self._emit("speech_end", audio=audio_bytes)

    # ── Called by session layer ───────────────────────────────────────────

    async def on_wake(self):
        """Wake word detected — open listening window."""
        if self._state == State.IDLE:
            await self._set_state(State.WAKE)

    async def on_speaking_start(self):
        self._barge_in_count = 0
        await self._set_state(State.SPEAKING)

    async def on_speaking_end(self, continuous: bool = True, timeout: float | None = None):
        t = timeout if timeout is not None else self._cfg.follow_up_timeout
        if continuous and t > 0:
            await self._set_state(State.FOLLOW_UP)
            self._follow_up_task = asyncio.create_task(self._follow_up_timer(t))
        else:
            await self._set_state(State.IDLE)

    async def _follow_up_timer(self, timeout: float):
        try:
            await asyncio.sleep(timeout)
            if self._state == State.FOLLOW_UP:
                logger.debug("Follow-up window expired → idle")
                await self._set_state(State.IDLE)
        except asyncio.CancelledError:
            pass

    def _cancel_follow_up(self):
        if self._follow_up_task and not self._follow_up_task.done():
            self._follow_up_task.cancel()
            self._follow_up_task = None

    async def interrupt(self):
        """Manual barge-in (e.g. from client sending type=interrupt)."""
        if self._state in (State.SPEAKING, State.FOLLOW_UP):
            self._barge_in_count = 0
            self._cancel_follow_up()
            self._speech_buf.clear()
            self._silence_count = 0
            self._speech_detected = False
            await self._set_state(State.LISTENING)
            await self._emit("interrupted")

    def pcm_to_float32(self, pcm_bytes: bytes) -> np.ndarray:
        arr = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        return arr / 32768.0
