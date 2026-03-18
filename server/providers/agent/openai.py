from __future__ import annotations

import logging
from typing import AsyncIterator

from .base import BaseAgent, AgentResponse, register

logger = logging.getLogger(__name__)


@register("openai")
class OpenAIAgent(BaseAgent):
    """
    OpenAI chat completion agent.
    Supports native token streaming via chat_stream().

    config keys:
      api_key    : OpenAI API key
      model      : model name (default: gpt-4o-mini)
      system     : system prompt (optional)
      base_url   : custom endpoint, e.g. for Azure or proxy (optional)
    """

    def __init__(self, config: dict):
        self._api_key = config.get("api_key", "")
        self._model = config.get("model", "gpt-4o-mini")
        self._system = config.get("system", "")
        self._base_url = config.get("base_url", None)
        self._history: list[dict] = []

    def _client(self):
        from openai import AsyncOpenAI
        kwargs = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return AsyncOpenAI(**kwargs)

    def _messages(self, text: str) -> list[dict]:
        msgs = []
        if self._system:
            msgs.append({"role": "system", "content": self._system})
        msgs += self._history
        msgs.append({"role": "user", "content": text})
        return msgs

    async def chat(self, text: str, session_id: str | None = None) -> AgentResponse:
        client = self._client()
        resp = await client.chat.completions.create(
            model=self._model,
            messages=self._messages(text),
        )
        reply = resp.choices[0].message.content or ""
        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": reply})
        return AgentResponse(text=reply, session_id=session_id)

    async def chat_stream(
        self, text: str, session_id: str | None = None
    ) -> AsyncIterator[str]:
        client = self._client()
        full = ""
        async with client.chat.completions.stream(
            model=self._model,
            messages=self._messages(text),
        ) as stream:
            async for event in stream:
                chunk = event.choices[0].delta.content if event.choices else None
                if chunk:
                    full += chunk
                    yield chunk
        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": full})
