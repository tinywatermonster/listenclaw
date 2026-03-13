from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class AgentResponse:
    text: str
    session_id: str | None = None
    tool_calls: list[dict] | None = None
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    """All agent providers implement this interface."""

    @abstractmethod
    async def chat(self, text: str, session_id: str | None = None) -> AgentResponse:
        """Send a message and get a complete response."""
        ...

    async def chat_stream(
        self, text: str, session_id: str | None = None
    ) -> AsyncIterator[str]:
        """
        Stream response tokens. Default implementation wraps chat().
        Override for providers that support native streaming.
        """
        response = await self.chat(text, session_id=session_id)
        yield response.text

    async def close(self) -> None:
        """Optional cleanup."""
        pass


# Registry
_registry: dict[str, type[BaseAgent]] = {}


def register(name: str):
    def decorator(cls: type[BaseAgent]):
        _registry[name] = cls
        return cls
    return decorator


def get_provider(name: str) -> type[BaseAgent]:
    if name not in _registry:
        raise ValueError(f"Unknown agent provider: {name!r}. Available: {list(_registry)}")
    return _registry[name]
