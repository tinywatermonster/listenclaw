from .base import BaseASR, ASRResult, register, get_provider
from . import whisper  # registers "whisper"

__all__ = ["BaseASR", "ASRResult", "register", "get_provider"]
