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
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

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
            # Run speech handling as a background task so audio input stays live
            asyncio.create_task(self._handle_speech(event.data["audio"]))
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

        # ── Agent + sentence-level streaming TTS ─────────────────────────
        # Agent tokens → sentence queue → TTS coroutine (runs concurrently)
        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
        tts_task = asyncio.create_task(
            self._stream_tts(sentence_queue, self._tts_cancel)
        )

        full_response = ""
        token_buf = ""
        try:
            async for chunk in self.agent.chat_stream(text, session_id=self.session_id):
                if self._tts_cancel.is_set():
                    break
                full_response += chunk
                token_buf += chunk
                await self._send({"type": "agent_chunk", "text": chunk})

                # Flush on sentence boundary
                while True:
                    m = _SENTENCE_END.search(token_buf)
                    if not m:
                        break
                    sentence = token_buf[: m.end()].strip()
                    token_buf = token_buf[m.end():]
                    if sentence:
                        await sentence_queue.put(sentence)

        except Exception as e:
            logger.error("Agent error: %s", e)
            await self._send({"type": "error", "message": f"Agent failed: {e}"})

        # Flush remaining buffer
        if token_buf.strip() and not self._tts_cancel.is_set():
            await sentence_queue.put(token_buf.strip())

        await sentence_queue.put(None)  # sentinel
        await self._send({"type": "agent_done", "text": full_response})
        logger.info("Agent: %r", full_response[:80])

        await tts_task

        if not self._tts_cancel.is_set():
            await self._send({"type": "tts_done"})
            await self.engine.on_speaking_end(
                continuous=self._continuous,
                timeout=self._follow_up_timeout,
            )
        # If cancelled, audio engine already switched to LISTENING via interrupt()

    async def _stream_tts(
        self, queue: asyncio.Queue[str | None], cancel: asyncio.Event
    ):
        """Consume sentences from queue, synthesize and stream audio."""
        await self.engine.on_speaking_start()
        try:
            while True:
                sentence = await queue.get()
                if sentence is None or cancel.is_set():
                    break
                try:
                    async for chunk in self.tts.synthesize_stream(sentence):
                        if cancel.is_set():
                            return
                        encoded = base64.b64encode(chunk).decode()
                        await self._send({"type": "tts_chunk", "data": encoded})
                except Exception as e:
                    logger.error("TTS error: %s", e)
                    await self._send({"type": "error", "message": f"TTS failed: {e}"})
        except asyncio.CancelledError:
            pass

    # ── WebSocket message loop ────────────────────────────────────────────

    async def handle(self):
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
            elif msg_type == "interrupt":
                await self.engine.interrupt()
            elif msg_type == "ping":
                await self._send({"type": "pong"})

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
