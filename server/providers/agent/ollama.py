from __future__ import annotations

import logging
from typing import AsyncIterator

from .base import BaseAgent, AgentResponse, register

logger = logging.getLogger(__name__)


@register("ollama")
class OllamaAgent(BaseAgent):
    """
    Ollama local LLM agent.
    Supports native token streaming via chat_stream().
    Requires Ollama running at base_url (default: http://localhost:11434).

    config keys:
      model    : model name (default: llama3.2)
      base_url : Ollama server URL (default: http://localhost:11434)
      system   : system prompt (optional)
    """

    def __init__(self, config: dict):
        self._model = config.get("model", "llama3.2")
        self._base_url = config.get("base_url", "http://localhost:11434")
        self._system = config.get("system", "")
        self._history: list[dict] = []

    def _messages(self, text: str) -> list[dict]:
        msgs = []
        if self._system:
            msgs.append({"role": "system", "content": self._system})
        msgs += self._history
        msgs.append({"role": "user", "content": text})
        return msgs

    async def chat(self, text: str, session_id: str | None = None) -> AgentResponse:
        import httpx
        async with httpx.AsyncClient(base_url=self._base_url, timeout=60) as client:
            resp = await client.post("/api/chat", json={
                "model": self._model,
                "messages": self._messages(text),
                "stream": False,
            })
            resp.raise_for_status()
            reply = resp.json()["message"]["content"]
        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": reply})
        return AgentResponse(text=reply, session_id=session_id)

    async def chat_stream(
        self, text: str, session_id: str | None = None
    ) -> AsyncIterator[str]:
        import httpx
        import json as _json
        full = ""
        async with httpx.AsyncClient(base_url=self._base_url, timeout=60) as client:
            async with client.stream("POST", "/api/chat", json={
                "model": self._model,
                "messages": self._messages(text),
                "stream": True,
            }) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = _json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full += chunk
                        yield chunk
                    if data.get("done"):
                        break
        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": full})
