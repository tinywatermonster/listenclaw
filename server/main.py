"""
ListenClaw WebSocket server entry point.

WebSocket protocol (JSON messages):

Client → Server:
  {"type": "audio",     "data": "<base64 int16 PCM>"}
  {"type": "interrupt"}
  {"type": "ping"}

Server → Client:
  {"type": "state",        "state": "idle|wake|listening|processing|speaking|follow_up"}
  {"type": "asr_result",   "text": "..."}
  {"type": "agent_chunk",  "text": "..."}   # streaming token
  {"type": "agent_done",   "text": "..."}   # full response
  {"type": "tts_chunk",    "data": "<base64 mp3>"}
  {"type": "tts_done"}
  {"type": "error",        "message": "..."}
  {"type": "pong"}

Sentence-level streaming:
  Agent tokens are buffered until a sentence boundary is found.
  Each sentence is sent to TTS immediately — audio starts playing
  before the full agent response is complete.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
import struct
import uuid
from contextlib import asynccontextmanager

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

try:
    import ctypes.util as _cu
    _orig_find = _cu.find_library
    def _patched_find(name):
        if name == 'opus':
            import os
            for p in ['/opt/homebrew/lib/libopus.dylib', '/usr/local/lib/libopus.dylib']:
                if os.path.exists(p):
                    return p
        return _orig_find(name)
    _cu.find_library = _patched_find
    import opuslib
    _cu.find_library = _orig_find
    _OPUS_AVAILABLE = True
except Exception:
    _OPUS_AVAILABLE = False
    logging.getLogger("listenclaw").warning("opuslib not available — hardware device endpoint disabled")

from .config import load_config, get
from .pipeline.core import AudioEngine, AudioEngineConfig, Event, State
from .router.intent import IntentRouter

# Providers (import triggers registration)
from .providers.asr import whisper       # noqa: F401
from .providers.agent import openclaw    # noqa: F401
from .providers.tts import edge_tts     # noqa: F401

from .providers.asr.base import get_provider as get_asr
from .providers.agent.base import get_provider as get_agent
from .providers.tts.base import get_provider as get_tts

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("listenclaw")

# Sentence boundary pattern (Chinese + Latin punctuation)
_SENTENCE_END = re.compile(r'[.!?。！？\n]')

# Strip text before sending to TTS: remove emoji, symbols, markdown
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FFFF"  # misc symbols and pictographs
    "\U00002600-\U000027BF"  # misc symbols
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "]+",
    flags=re.UNICODE,
)
_MD_RE = re.compile(r'[*_`#>~|\\]')

def _clean_for_tts(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = _MD_RE.sub("", text)
    return text.strip()

config: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config
    config = load_config()
    logger.info(
        "ListenClaw starting — ASR:%s  Agent:%s  TTS:%s",
        get(config, "asr", "provider"),
        get(config, "agent", "provider"),
        get(config, "tts", "provider"),
    )
    yield


app = FastAPI(title="ListenClaw", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Session ───────────────────────────────────────────────────────────────────

class Session:
    def __init__(self, ws: WebSocket, cfg: dict):
        self._ws = ws
        self._cfg = cfg
        self._continuous = get(cfg, "session", "continuous_conversation", default=True)
        self._follow_up_timeout = float(get(cfg, "session", "follow_up_timeout", default=8))

        asr_name = get(cfg, "asr", "provider", default="whisper")
        agent_name = get(cfg, "agent", "provider", default="openclaw")
        tts_name = get(cfg, "tts", "provider", default="edge_tts")

        self.asr = get_asr(asr_name)(get(cfg, "asr", asr_name) or {})
        self.agent = get_agent(agent_name)(get(cfg, "agent", agent_name) or {})
        self.tts = get_tts(tts_name)(get(cfg, "tts", tts_name) or {})
        self.router = IntentRouter(cfg)
        self.session_id: str | None = None

        # Cancellation token for TTS: replaced on each new utterance
        self._tts_cancel: asyncio.Event = asyncio.Event()
        # Current speech pipeline task
        self._speech_task: asyncio.Task | None = None
        # Utterance queue: PTT audio waits here while a pipeline is running
        self._utterance_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._queue_worker_task: asyncio.Task | None = None

        audio_cfg = AudioEngineConfig(
            sample_rate=get(cfg, "audio", "sample_rate", default=16000),
            chunk_ms=get(cfg, "audio", "chunk_ms", default=30),
            vad_aggressiveness=get(cfg, "audio", "vad_aggressiveness", default=2),
            follow_up_timeout=self._follow_up_timeout,
        )
        self.engine = AudioEngine(audio_cfg, self._on_event)

    async def _send(self, msg: dict):
        try:
            await self._ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    async def _on_event(self, event: Event):
        t = event.type
        if t == "state_change":
            await self._send({"type": "state", "state": event.data["state"]})
        elif t == "speech_end":
            # Cancel any in-flight pipeline before starting new one
            if self._speech_task and not self._speech_task.done():
                self._tts_cancel.set()
                self._speech_task.cancel()
            self._tts_cancel = asyncio.Event()
            self._speech_task = asyncio.create_task(
                self._handle_speech(event.data["audio"])
            )
        elif t == "interrupted":
            # Signal TTS coroutine to stop
            self._tts_cancel.set()
            await self._send({"type": "state", "state": "listening"})

    # ── Speech pipeline ───────────────────────────────────────────────────

    async def _handle_speech(self, audio_bytes: bytes):
        sample_rate = get(self._cfg, "audio", "sample_rate", default=16000)
        audio_f32 = self.engine.pcm_to_float32(audio_bytes)

        # Reset barge-in token for this turn
        self._tts_cancel = asyncio.Event()

        # ── ASR ──────────────────────────────────────────────────────────
        try:
            asr_result = await self.asr.transcribe(audio_f32, sample_rate)
        except Exception as e:
            logger.error("ASR error: %s", e)
            await self._send({"type": "error", "message": f"ASR failed: {e}"})
            await self.engine.on_speaking_end(continuous=False)
            return

        text = asr_result.text.strip()
        if not text:
            await self.engine.on_speaking_end(
                continuous=self._continuous,
                timeout=self._follow_up_timeout,
            )
            return

        await self._send({"type": "asr_result", "text": text})
        logger.info("ASR: %r", text)

        # ── Agent: run silently, collect full response ────────────────────
        full_response = ""
        try:
            async for chunk in self.agent.chat_stream(text, session_id=self.session_id):
                if self._tts_cancel.is_set():
                    return
                full_response += chunk
        except Exception as e:
            logger.error("Agent error: %s", e)
            await self._send({"type": "error", "message": f"Agent failed: {e}"})
            return

        logger.info("Agent done: %r", full_response[:80])

        # ── TTS: generate full audio, then push task_complete ────────────
        tts_text = _clean_for_tts(full_response)
        audio_b64 = ""
        if tts_text:
            try:
                chunks = []
                async for chunk in self.tts.synthesize_stream(tts_text):
                    if self._tts_cancel.is_set():
                        return
                    chunks.append(chunk)
                audio_b64 = base64.b64encode(b"".join(chunks)).decode()
                logger.info("TTS ready: %d bytes", len(b"".join(chunks)))
            except Exception as e:
                logger.error("TTS error: %s", e)

        # Push single notification with text + audio together
        await self._send({"type": "task_complete", "text": full_response, "audio": audio_b64})

        await self.engine.on_speaking_end(
            continuous=self._continuous,
            timeout=self._follow_up_timeout,
        )

    # ── Utterance queue ───────────────────────────────────────────────────

    async def _queue_worker(self):
        """Process utterances one at a time from the queue."""
        while True:
            try:
                pcm = await self._utterance_queue.get()
            except asyncio.CancelledError:
                break
            self._tts_cancel = asyncio.Event()
            await self._send({"type": "state", "state": "processing"})
            self._speech_task = asyncio.create_task(self._handle_speech(pcm))
            try:
                await self._speech_task
            except asyncio.CancelledError:
                pass
            finally:
                self._utterance_queue.task_done()

    async def _clear_utterance_queue(self):
        """Drain the queue and cancel the in-flight speech task."""
        while not self._utterance_queue.empty():
            try:
                self._utterance_queue.get_nowait()
                self._utterance_queue.task_done()
            except asyncio.QueueEmpty:
                break
        self._tts_cancel.set()
        if self._speech_task and not self._speech_task.done():
            self._speech_task.cancel()

    # ── WebSocket message loop ────────────────────────────────────────────

    async def handle(self):
        self._queue_worker_task = asyncio.create_task(self._queue_worker())
        while True:
            try:
                raw = await self._ws.receive_text()
                msg = json.loads(raw)
            except WebSocketDisconnect:
                break
            except Exception:
                continue

            msg_type = msg.get("type", "")
            if msg_type == "audio":
                pcm = base64.b64decode(msg["data"])
                await self.engine.push_audio(pcm)
            elif msg_type == "ptt_audio":
                # PTT mode: enqueue utterance; queue worker processes them serially
                pcm = base64.b64decode(msg["data"])
                await self._utterance_queue.put(pcm)
                pending = self._utterance_queue.qsize()
                if pending > 0:
                    await self._send({"type": "queued", "position": pending})
            elif msg_type == "interrupt":
                await self._clear_utterance_queue()
                await self.engine.interrupt()
            elif msg_type == "ping":
                await self._send({"type": "pong"})

    async def close(self):
        if self._queue_worker_task:
            self._queue_worker_task.cancel()
        await self.asr.close()
        await self.agent.close()
        await self.tts.close()


# ── Xiaozhi device protocol helpers ──────────────────────────────────────────

_OPUS_FRAME_MS = 60
_OPUS_SAMPLE_RATE = 16000
_OPUS_FRAME_SAMPLES = _OPUS_SAMPLE_RATE * _OPUS_FRAME_MS // 1000  # 960


def _pack_opus_frame(opus_data: bytes) -> bytes:
    """Wrap Opus payload in BinaryProtocol3 frame (xiaozhi format)."""
    return bytes([0x00, 0x00]) + struct.pack(">H", len(opus_data)) + opus_data


def _unpack_opus_payload(data: bytes) -> bytes | None:
    """Extract Opus payload from BinaryProtocol3 frame."""
    if len(data) < 4:
        return None
    payload_size = struct.unpack_from(">H", data, 2)[0]
    if len(data) < 4 + payload_size:
        return None
    return data[4:4 + payload_size]


async def _mp3_to_opus_frames(mp3_bytes: bytes) -> list[bytes]:
    """Convert MP3 bytes → PCM via ffmpeg → list of Opus frames."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", "pipe:0", "-loglevel", "quiet",
        "-ar", str(_OPUS_SAMPLE_RATE), "-ac", "1", "-f", "s16le", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    pcm_data, _ = await proc.communicate(input=mp3_bytes)
    if not pcm_data or not _OPUS_AVAILABLE:
        return []
    encoder = opuslib.Encoder(_OPUS_SAMPLE_RATE, 1, opuslib.APPLICATION_VOIP)
    frame_bytes = _OPUS_FRAME_SAMPLES * 2
    frames = []
    for i in range(0, len(pcm_data), frame_bytes):
        chunk = pcm_data[i:i + frame_bytes].ljust(frame_bytes, b'\x00')
        try:
            frames.append(encoder.encode(chunk, _OPUS_FRAME_SAMPLES))
        except Exception:
            pass
    return frames


# ── Hardware device session (xiaozhi protocol) ────────────────────────────────

class DeviceSession:
    def __init__(self, ws: WebSocket, cfg: dict):
        self._ws = ws
        self._cfg = cfg
        self._session_id = str(uuid.uuid4())[:8]
        self._proto_version = 1  # negotiated from device hello
        self._opus_frames: list[bytes] = []
        self._recording = False
        self._recording_mode = "manual"
        self._last_speech_time: float = 0.0
        self._vad_decoder = None  # lazy-init opuslib.Decoder for VAD
        self._silence_task: asyncio.Task | None = None
        self._cancel = asyncio.Event()
        self._speech_task: asyncio.Task | None = None
        self._approve_event: asyncio.Event | None = None

        asr_name = get(cfg, "asr", "provider", default="whisper")
        agent_name = get(cfg, "agent", "provider", default="openclaw")
        tts_name = get(cfg, "tts", "provider", default="edge_tts")
        self.asr = get_asr(asr_name)(get(cfg, "asr", asr_name) or {})
        self.agent = get_agent(agent_name)(get(cfg, "agent", agent_name) or {})
        self.tts = get_tts(tts_name)(get(cfg, "tts", tts_name) or {})

    async def _send_json(self, msg: dict):
        try:
            await self._ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass

    async def _send_audio(self, opus_data: bytes):
        try:
            if self._proto_version == 3:
                await self._ws.send_bytes(_pack_opus_frame(opus_data))
            else:
                await self._ws.send_bytes(opus_data)  # version 1/2: raw Opus
        except Exception:
            pass

    async def handle(self):
        # Handshake: wait for hello
        try:
            raw = await asyncio.wait_for(self._ws.receive_text(), timeout=15.0)
            hello = json.loads(raw)
        except Exception:
            return
        if hello.get("type") != "hello":
            return

        self._proto_version = hello.get("version", 1)
        await self._send_json({
            "type": "hello", "transport": "websocket",
            "session_id": self._session_id, "version": self._proto_version,
            "audio_params": {"format": "opus", "sample_rate": _OPUS_SAMPLE_RATE,
                             "channels": 1, "frame_duration": _OPUS_FRAME_MS},
        })
        logger.info("Device handshake OK session=%s proto_version=%d",
                    self._session_id, self._proto_version)

        # Message loop
        while True:
            try:
                msg = await self._ws.receive()
            except WebSocketDisconnect:
                break
            except Exception:
                break
            if "text" in msg:
                try:
                    await self._handle_json(json.loads(msg["text"]))
                except Exception:
                    pass
            elif "bytes" in msg:
                await self._handle_binary(msg["bytes"])

    async def _greet(self):
        """Play a short greeting after handshake so user knows device is connected."""
        try:
            await asyncio.sleep(0.5)
            greeting = "已连接"
            mp3_chunks = []
            async for chunk in self.tts.synthesize_stream(greeting):
                mp3_chunks.append(chunk)
            opus_out = await _mp3_to_opus_frames(b"".join(mp3_chunks))
            if not opus_out:
                return
            await self._send_json({"type": "tts", "state": "start", "session_id": self._session_id})
            for frame in opus_out:
                await self._send_audio(frame)
                await asyncio.sleep(_OPUS_FRAME_MS / 1000 * 0.8)
            await self._send_json({"type": "tts", "state": "stop", "session_id": self._session_id})
        except Exception as e:
            logger.warning("Greeting failed: %s", e)

    async def _handle_json(self, msg: dict):
        t = msg.get("type")
        state = msg.get("state")
        if t == "listen":
            if state == "detect":
                logger.info("Device wake word: %s", msg.get("text", ""))
            elif state == "start":
                self._opus_frames = []
                self._recording = True
                self._recording_mode = msg.get("mode", "manual")
                self._last_speech_time = asyncio.get_event_loop().time()
                logger.info("Device recording start (mode=%s)", self._recording_mode)
                if self._recording_mode == "auto":
                    if self._silence_task:
                        self._silence_task.cancel()
                    self._silence_task = asyncio.create_task(self._silence_watchdog())
            elif state == "stop":
                await self._commit_recording()
        elif t == "approve":
            logger.info("User approved pending response")
            if self._approve_event:
                self._approve_event.set()
        elif t == "abort":
            self._cancel.set()
            if self._silence_task:
                self._silence_task.cancel()
                self._silence_task = None
            if self._speech_task and not self._speech_task.done():
                self._speech_task.cancel()

    async def _commit_recording(self):
        self._recording = False
        if self._silence_task:
            self._silence_task.cancel()
            self._silence_task = None
        frames = self._opus_frames[:]
        self._opus_frames = []
        logger.info("Device recording stop (%d frames)", len(frames))
        if frames:
            self._cancel = asyncio.Event()
            self._speech_task = asyncio.create_task(self._process(frames))

    async def _silence_watchdog(self):
        """Auto-mode: trigger processing after 800ms of silence (energy-based)."""
        await asyncio.sleep(0.5)  # minimum recording length
        while self._recording:
            await asyncio.sleep(0.1)
            silence = asyncio.get_event_loop().time() - self._last_speech_time
            if silence >= 0.8 and self._opus_frames:
                logger.info("Silence detected (%.1fs), auto-committing %d frames",
                            silence, len(self._opus_frames))
                await self._commit_recording()
                return

    async def _handle_binary(self, data: bytes):
        if not self._recording:
            return
        if self._proto_version == 3:
            payload = _unpack_opus_payload(data)
        else:
            payload = data  # version 1/2: raw Opus, no header
        if payload:
            self._opus_frames.append(payload)
            # Decode and check RMS energy to detect speech vs silence
            if _OPUS_AVAILABLE and self._recording_mode == "auto":
                try:
                    if self._vad_decoder is None:
                        self._vad_decoder = opuslib.Decoder(_OPUS_SAMPLE_RATE, 1)
                    pcm = self._vad_decoder.decode(payload, _OPUS_FRAME_SAMPLES)
                    rms = np.sqrt(np.mean(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) ** 2))
                    if rms > 200:  # ~0.6% of max — speech threshold
                        self._last_speech_time = asyncio.get_event_loop().time()
                except Exception:
                    pass

    async def _process(self, opus_frames: list[bytes]):
        try:
            # Decode Opus → PCM float32
            decoder = opuslib.Decoder(_OPUS_SAMPLE_RATE, 1)
            pcm_chunks = []
            for frame in opus_frames:
                try:
                    pcm_chunks.append(decoder.decode(frame, _OPUS_FRAME_SAMPLES))
                except Exception:
                    pass
            if not pcm_chunks:
                return
            pcm_int16 = np.frombuffer(b"".join(pcm_chunks), dtype=np.int16)
            pcm_f32 = pcm_int16.astype(np.float32) / 32768.0

            # ASR
            try:
                result = await self.asr.transcribe(pcm_f32, _OPUS_SAMPLE_RATE)
            except Exception as e:
                logger.error("Device ASR error: %s", e)
                return
            text = result.text.strip()
            if not text:
                return
            logger.info("Device ASR: %r", text)
            await self._send_json({"type": "stt", "text": text, "session_id": self._session_id})

            # Agent
            full_response = ""
            async for chunk in self.agent.chat_stream(text, session_id=self._session_id):
                if self._cancel.is_set():
                    return
                full_response += chunk
            logger.info("Device Agent: %r", full_response[:80])
            await self._send_json({
                "type": "llm", "text": full_response,
                "emotion": "neutral", "session_id": self._session_id,
            })

            # Notify device — wait for user approval before playing
            self._approve_event = asyncio.Event()
            await self._send_json({"type": "tts", "state": "pending", "session_id": self._session_id})
            logger.info("Pending approval (3s timeout)...")
            try:
                await asyncio.wait_for(self._approve_event.wait(), timeout=3.0)
                logger.info("User approved")
            except asyncio.TimeoutError:
                logger.info("Approval timeout, playing anyway")
            self._approve_event = None
            if self._cancel.is_set():
                return

            # TTS → Opus
            tts_text = _clean_for_tts(full_response)
            if not tts_text:
                return
            mp3_chunks = []
            async for chunk in self.tts.synthesize_stream(tts_text):
                if self._cancel.is_set():
                    return
                mp3_chunks.append(chunk)
            opus_out = await _mp3_to_opus_frames(b"".join(mp3_chunks))
            if not opus_out:
                return

            await self._send_json({"type": "tts", "state": "start", "session_id": self._session_id})
            for frame in opus_out:
                if self._cancel.is_set():
                    break
                await self._send_audio(frame)
                await asyncio.sleep(_OPUS_FRAME_MS / 1000 * 0.8)  # pace slightly faster than real-time
            await self._send_json({"type": "tts", "state": "stop", "session_id": self._session_id})

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Device pipeline error: %s", e)

    async def close(self):
        await self.asr.close()
        await self.agent.close()
        await self.tts.close()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected: %s", websocket.client)
    session = Session(websocket, config)
    try:
        await session.handle()
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
        logger.info("Client disconnected: %s", websocket.client)


@app.websocket("/ws/device")
async def ws_device_endpoint(websocket: WebSocket):
    """Hardware device endpoint — xiaozhi protocol (Opus audio)."""
    await websocket.accept()
    logger.info("Device connected: %s", websocket.client)
    session = DeviceSession(websocket, config)
    try:
        await session.handle()
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
        logger.info("Device disconnected: %s", websocket.client)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "asr": get(config, "asr", "provider"),
        "agent": get(config, "agent", "provider"),
        "tts": get(config, "tts", "provider"),
    }


if __name__ == "__main__":
    host = get(config, "server", "host", default="0.0.0.0")
    port = int(get(config, "server", "port", default=8765))
    uvicorn.run("server.main:app", host=host, port=port, reload=False)
