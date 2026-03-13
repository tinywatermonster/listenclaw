import asyncio
import json
import logging
from .base import BaseAgent, AgentResponse, register

logger = logging.getLogger(__name__)


@register("openclaw")
class OpenClawAgent(BaseAgent):
    """
    OpenClaw agent adapter.
    Supports two modes:
      - cli: subprocess call to `openclaw agent --message ... --json`
      - websocket: connect to OpenClaw gateway at ws://localhost:18789
    """

    def __init__(self, config: dict):
        self._mode = config.get("mode", "cli")
        self._agent = config.get("agent", "main")
        self._cli_bin = config.get("cli_bin", "openclaw")
        self._ws_url = config.get("websocket_url", "ws://localhost:18789")
        self._token = config.get("token", "")

    # ── CLI mode ──────────────────────────────────────────────────────────

    async def _chat_cli(self, text: str, session_id: str | None) -> AgentResponse:
        cmd = [
            self._cli_bin, "agent",
            "--message", text,
            "--agent", self._agent,
            "--json",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            raise RuntimeError("OpenClaw CLI timed out after 60s")
        except FileNotFoundError:
            raise RuntimeError(
                f"openclaw binary not found at {self._cli_bin!r}. "
                "Is OpenClaw installed?"
            )

        if proc.returncode != 0:
            raise RuntimeError(
                f"OpenClaw CLI exited {proc.returncode}: {stderr.decode().strip()}"
            )

        raw = stdout.decode().strip()
        try:
            data = json.loads(raw)
            reply_text = (
                data.get("response")
                or data.get("text")
                or data.get("content")
                or raw
            )
        except json.JSONDecodeError:
            reply_text = raw

        return AgentResponse(text=reply_text, session_id=session_id)

    # ── WebSocket mode ────────────────────────────────────────────────────

    async def _chat_ws(self, text: str, session_id: str | None) -> AgentResponse:
        import websockets

        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            async with websockets.connect(self._ws_url, additional_headers=headers) as ws:
                payload = {
                    "type": "message",
                    "content": text,
                    "agent": self._agent,
                }
                if session_id:
                    payload["session_id"] = session_id

                await ws.send(json.dumps(payload))

                chunks = []
                async for raw in ws:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")
                    if msg_type == "text":
                        chunks.append(msg.get("content", ""))
                    elif msg_type == "done":
                        break
                    elif msg_type == "error":
                        raise RuntimeError(f"OpenClaw WS error: {msg.get('message')}")

                return AgentResponse(
                    text="".join(chunks),
                    session_id=msg.get("session_id") or session_id,
                )
        except Exception as e:
            raise RuntimeError(f"OpenClaw WebSocket failed: {e}") from e

    # ── Public interface ──────────────────────────────────────────────────

    async def chat(self, text: str, session_id: str | None = None) -> AgentResponse:
        logger.debug("OpenClaw [%s] <- %r", self._mode, text)
        if self._mode == "websocket":
            return await self._chat_ws(text, session_id)
        return await self._chat_cli(text, session_id)
