from .base import BaseTTS, TTSConfig, register, get_provider
from . import edge_tts  # registers "edge_tts"

__all__ = ["BaseTTS", "TTSConfig", "register", "get_provider"]
