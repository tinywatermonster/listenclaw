from .base import BaseTTS, TTSConfig, register, get_provider
from . import edge_tts    # registers "edge_tts"
from . import elevenlabs  # registers "elevenlabs"
from . import qwen_tts    # registers "qwen_tts"
from . import aliyun      # registers "aliyun"

__all__ = ["BaseTTS", "TTSConfig", "register", "get_provider"]
