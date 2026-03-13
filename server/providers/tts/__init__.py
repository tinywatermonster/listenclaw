from .base import BaseTTS, TTSConfig, register, get_provider
from . import edge_tts    # registers "edge_tts"
from . import elevenlabs  # registers "elevenlabs"

__all__ = ["BaseTTS", "TTSConfig", "register", "get_provider"]
