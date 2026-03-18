from .base import BaseAgent, AgentResponse, register, get_provider
from . import openclaw  # registers "openclaw"
from . import openai    # registers "openai"   # noqa: F401
from . import claude    # registers "claude"   # noqa: F401
from . import ollama    # registers "ollama"   # noqa: F401

__all__ = ["BaseAgent", "AgentResponse", "register", "get_provider"]
