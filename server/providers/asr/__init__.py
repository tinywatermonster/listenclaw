from .base import BaseASR, ASRResult, register, get_provider
from . import whisper     # registers "whisper"
from . import elevenlabs  # registers "elevenlabs"
from . import funasr      # registers "funasr" (SenseVoice)
from . import aliyun      # registers "aliyun"

__all__ = ["BaseASR", "ASRResult", "register", "get_provider"]
