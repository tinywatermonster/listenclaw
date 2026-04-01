import json
import logging
import time
from typing import AsyncIterator
from .base import BaseTTS, TTSConfig, register

logger = logging.getLogger(__name__)


@register("aliyun")
class AliyunTTS(BaseTTS):
    """
    Alibaba Cloud NLS 语音合成 (TTS).
    pip install aliyun-python-sdk-core
    Requires: access_key_id, access_key_secret, app_key in config.
    """

    def __init__(self, config: dict):
        self._akid     = config["access_key_id"]
        self._aksecret = config["access_key_secret"]
        self._appkey   = config["app_key"]
        self._region   = config.get("region", "cn-shanghai")
        self._voice    = config.get("voice", "aicheng")      # 男声；女声用 aiqi / xiaoyun
        self._format   = config.get("format", "mp3")
        self._token    = None
        self._token_expire = 0

    def _ensure_token(self):
        if self._token and time.time() < self._token_expire - 60:
            return
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkcore.request import CommonRequest
        client = AcsClient(self._akid, self._aksecret, self._region)
        req = CommonRequest()
        req.set_method("POST")
        req.set_domain(f"nls-meta.{self._region}.aliyuncs.com")
        req.set_version("2019-02-28")
        req.set_action_name("CreateToken")
        resp = json.loads(client.do_action_with_exception(req))
        self._token = resp["Token"]["Id"]
        self._token_expire = resp["Token"]["ExpireTime"]
        logger.info("Aliyun NLS token refreshed")

    async def synthesize(self, text: str, config: TTSConfig | None = None) -> bytes:
        chunks = []
        async for chunk in self.synthesize_stream(text, config):
            chunks.append(chunk)
        return b"".join(chunks)

    async def synthesize_stream(
        self, text: str, config: TTSConfig | None = None
    ) -> AsyncIterator[bytes]:
        import asyncio
        import http.client

        self._ensure_token()

        voice  = (config and config.voice) or self._voice
        token  = self._token
        appkey = self._appkey
        region = self._region
        fmt    = self._format
        logger.info("Aliyun TTS synthesizing: %r (voice=%s)", text[:40], voice)

        def _call():
            payload = json.dumps({
                "appkey": appkey,
                "token":  token,
                "text":   text,
                "format": fmt,
                "sample_rate": 16000,
                "voice":  voice,
                "volume": 60,
                "speech_rate": 0,
            }, ensure_ascii=False).encode("utf-8")
            host = f"nls-gateway-{region}.aliyuncs.com"
            conn = http.client.HTTPSConnection(host, timeout=15)
            conn.request(
                "POST", "/stream/v1/tts",
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            content_type = resp.getheader("Content-Type", "")
            body = resp.read()
            if "audio" in content_type:
                return body
            raise RuntimeError(f"Aliyun TTS error: {json.loads(body)}")

        audio_bytes = await asyncio.get_event_loop().run_in_executor(None, _call)
        logger.info("Aliyun TTS done: %d bytes", len(audio_bytes))
        yield audio_bytes
