from __future__ import annotations

import logging
from typing import AsyncIterator

from .base import BaseAgent, AgentResponse, register

logger = logging.getLogger(__name__)


@register("claude")
class ClaudeAgent(BaseAgent):
    """
    Anthropic Claude agent.
    Supports native token streaming via chat_stream().

    config keys:
      api_key : Anthropic API key
      model   : model name (default: claude-haiku-4-5-20251001)
      system  : system prompt (optional)
    """

    def __init__(self, config: dict):
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "claude-haiku-4-5-20251001")
        self._system = config.get("system", "")
        self._history: list[dict] = []

    def _client(self):
        from anthropic import AsyncAnthropic
        return AsyncAnthropic(api_key=self._api_key)

    async def chat(self, text: str, session_id: str | None = None) -> AgentResponse:
        client = self._client()
        msgs = self._history + [{"role": "user", "content": text}]
        kwargs = {"model": self._model, "max_tokens": 1024, "messages": msgs}
        if self._system:
            kwargs["system"] = self._system
        resp = await client.messages.create(**kwargs)
        reply = resp.content[0].text
        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": reply})
        return AgentResponse(text=reply, session_id=session_id)

    async def chat_stream(
        self, text: str, session_id: str | None = None
    ) -> AsyncIterator[str]:
        client = self._client()
        msgs = self._history + [{"role": "user", "content": text}]
        kwargs = {"model": self._model, "max_tokens": 1024, "messages": msgs}
        if self._system:
            kwargs["system"] = self._system
        full = ""
        async with client.messages.stream(**kwargs) as stream:
            async for chunk in stream.text_stream:
                full += chunk
                yield chunk
        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": full})
