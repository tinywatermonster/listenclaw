#!/usr/bin/env python3
"""
ListenClaw CLI demo — end-to-end voice test.

Usage:
  python scripts/demo_cli.py [--url ws://localhost:8765/ws]

Requires:
  pip install sounddevice pyaudio pydub

Controls:
  SPACE   Push-to-talk (hold to speak, release to send)
  i       Manual interrupt (stop current TTS)
  q       Quit
"""

import argparse
import asyncio
import base64
import json
import sys
import threading
import time
from collections import deque
from io import BytesIO

import numpy as np
import websockets

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16
CHUNK_MS = 30
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_MS / 1000)

STATE_COLORS = {
    "idle":       "\033[90m",   # grey
    "wake":       "\033[35m",   # magenta
    "listening":  "\033[32m",   # green
    "processing": "\033[33m",   # yellow
    "speaking":   "\033[34m",   # blue
    "follow_up":  "\033[36m",   # cyan
}
RESET = "\033[0m"
BOLD  = "\033[1m"


def _color(state: str, text: str) -> str:
    return f"{STATE_COLORS.get(state, '')}{text}{RESET}"


class CLIDemo:
    def __init__(self, url: str):
        self._url = url
        self._recording = False
        self._audio_buf: deque = deque()
        self._ws = None
        self._current_state = "idle"
        self._tts_buf = bytearray()
        self._stream = None

    def _record_callback(self, indata, frames, time_info, status):
        if self._recording:
            self._audio_buf.append(indata.copy())

    async def _send_audio_loop(self):
        while True:
            await asyncio.sleep(CHUNK_MS / 1000)
            if self._audio_buf and self._recording:
                frames = []
                while self._audio_buf:
                    frames.append(self._audio_buf.popleft())
                pcm = np.concatenate(frames, axis=0).astype(np.int16).tobytes()
                encoded = base64.b64encode(pcm).decode()
                try:
                    await self._ws.send(json.dumps({"type": "audio", "data": encoded}))
                except Exception:
                    break

    async def _play_audio(self, data: bytes):
        """Play MP3 audio bytes via pydub + sounddevice (uses system default output)."""
        try:
            import sounddevice as sd
            from pydub import AudioSegment
            seg = AudioSegment.from_file(BytesIO(data), format="mp3")
            rate = seg.frame_rate
            pcm = seg.set_channels(1).set_sample_width(2)
            arr = np.frombuffer(pcm.raw_data, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(arr, rate)
            # Poll stream state instead of blocking sd.wait() — avoids CoreAudio thread issues
            while sd.get_stream().active:
                await asyncio.sleep(0.05)
        except ImportError:
            sys.stderr.write("[demo] pydub/sounddevice not installed — skipping playback\n")
        except Exception as e:
            sys.stderr.write(f"[demo] playback error: {e}\n")

    async def _receive_loop(self):
        tts_chunks = []
        async for raw in self._ws:
            msg = json.loads(raw)
            t = msg.get("type", "")

            if t == "state":
                self._current_state = msg["state"]
                label = _color(msg["state"], f"[{msg['state'].upper()}]")
                print(f"\r{label}          ", end="", flush=True)

            elif t == "asr_result":
                print(f"\n{BOLD}You:{RESET} {msg['text']}")

            elif t == "agent_chunk":
                print(msg["text"], end="", flush=True)

            elif t == "agent_done":
                print()  # newline after streaming tokens

            elif t == "tts_chunk":
                tts_chunks.append(base64.b64decode(msg["data"]))

            elif t == "tts_done":
                if tts_chunks:
                    audio = b"".join(tts_chunks)
                    tts_chunks.clear()
                    asyncio.create_task(self._play_audio(audio))

            elif t == "error":
                print(f"\n\033[31m[error] {msg['message']}\033[0m")

    async def _keyboard_loop(self):
        """Non-blocking keyboard via stdin thread."""
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def read_keys():
            import tty
            import termios
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while True:
                    ch = sys.stdin.read(1)
                    loop.call_soon_threadsafe(queue.put_nowait, ch)
                    if ch == "q":
                        break
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)

        threading.Thread(target=read_keys, daemon=True).start()

        print(f"\n{BOLD}ListenClaw CLI Demo{RESET}")
        print("  SPACE = push-to-talk  |  i = interrupt  |  q = quit\n")
        print(_color("idle", "[IDLE]"), end="", flush=True)

        while True:
            ch = await queue.get()
            if ch == " ":
                if not self._recording:
                    self._recording = True
                    print(f"\r{_color('listening', '[LISTENING]')} 🎙 speaking…    ", end="", flush=True)
                else:
                    self._recording = False
                    print(f"\r{_color('processing', '[PROCESSING]')} ✓ sent           ", end="", flush=True)
            elif ch == "i":
                await self._ws.send(json.dumps({"type": "interrupt"}))
                print(f"\r{_color('listening', '[INTERRUPT]')}                   ", end="", flush=True)
            elif ch == "q":
                print("\nBye.")
                return

    async def run(self):
        try:
            import sounddevice as sd
        except ImportError:
            sys.exit("sounddevice not installed. Run: pip install sounddevice")

        print(f"Connecting to {self._url} …")
        async with websockets.connect(self._url) as ws:
            self._ws = ws
            print("Connected.\n")

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_FRAMES,
                callback=self._record_callback,
            ):
                await asyncio.gather(
                    self._receive_loop(),
                    self._send_audio_loop(),
                    self._keyboard_loop(),
                )


def main():
    parser = argparse.ArgumentParser(description="ListenClaw CLI demo")
    parser.add_argument("--url", default="ws://localhost:8765/ws")
    args = parser.parse_args()

    try:
        asyncio.run(CLIDemo(args.url).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
