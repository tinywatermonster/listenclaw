import json
import logging
import time
import numpy as np
from .base import BaseASR, ASRResult, register

logger = logging.getLogger(__name__)


@register("aliyun")
class AliyunASR(BaseASR):
    """
    Alibaba Cloud NLS 一句话识别 (Short Sentence ASR).
    pip install aliyun-python-sdk-core
    Requires: access_key_id, access_key_secret, app_key in config.
    """

    def __init__(self, config: dict):
        self._akid     = config["access_key_id"]
        self._aksecret = config["access_key_secret"]
        self._appkey   = config["app_key"]
        self._region   = config.get("region", "cn-shanghai")
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
        logger.info("Aliyun NLS token refreshed, expires at %d", self._token_expire)

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> ASRResult:
        import asyncio
        import http.client

        self._ensure_token()

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            import librosa
            audio = librosa.resample(audio, orig_sr=sample_rate, target_sr=16000)

        # Convert float32 → int16 PCM bytes
        pcm = (audio.astype(np.float32) * 32767).clip(-32768, 32767).astype(np.int16).tobytes()

        token   = self._token
        appkey  = self._appkey
        region  = self._region

        def _call():
            host = f"nls-gateway-{region}.aliyuncs.com"
            path = (
                f"/stream/v1/asr"
                f"?appkey={appkey}"
                f"&format=pcm&sample_rate=16000"
                f"&enable_punctuation_prediction=true"
                f"&enable_inverse_text_normalization=true"
            )
            headers = {
                "X-NLS-Token": token,
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(pcm)),
            }
            conn = http.client.HTTPSConnection(host, timeout=15)
            conn.request("POST", path, body=pcm, headers=headers)
            resp = conn.getresponse()
            data = json.loads(resp.read())
            if data.get("status") == 20000000:
                return data.get("result", "")
            raise RuntimeError(f"Aliyun ASR error {data.get('status')}: {data.get('message')}")

        text = await asyncio.get_event_loop().run_in_executor(None, _call)
        logger.info("Aliyun ASR: %r", text)
        return ASRResult(text=text, language="zh")
