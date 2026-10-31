"""语音识别适配层：调用阿里云百炼 Qwen-ASR（qwen3-asr-flash）转写文字。

调用方式遵循官方文档的 OpenAI 兼容 Chat Completions 协议：
- 音频字节编码为 Data URL（``data:<mediatype>;base64,<data>``），
  作为 ``input_audio`` 内容块放在 user 消息中；
- ``stream=False`` 非实时识别；
- 地域/Workspace 专属 Base URL、API Key、模型名均从环境变量读取。

与文本生成（QwenGenerator）完全分离：不复用其客户端、模型或密钥配置，
也不会把录音发送给文本生成模型。

日志只记录类型/状态码/耗时，不包含 API Key 或录音内容。
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

# 从项目根目录 .env 读取 ASR 配置（与 generator/settings 一致）
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

logger = logging.getLogger("ikgr.speech")

DEFAULT_MODEL = "qwen3-asr-flash"
# 单次转写请求超时（秒）；本校录音限制在 30 秒以内，30 秒足够
REQUEST_TIMEOUT_SECONDS = 30.0


class AsrError(Exception):
    """语音识别失败；API 层据此映射 HTTP 状态码与统一错误结构。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        code: str = "ASR_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class SpeechTranscriber:
    """短音频转写：file_bytes + content_type -> 文本。"""

    def __init__(self):
        self._api_key = os.getenv("ASR_API_KEY")
        self._base_url = os.getenv("ASR_BASE_URL")
        self._model = os.getenv("ASR_MODEL") or DEFAULT_MODEL
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._base_url)

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url.rstrip("/"),
                timeout=REQUEST_TIMEOUT_SECONDS,
                max_retries=0,
            )
        return self._client

    def transcribe(
        self,
        file_bytes: bytes,
        content_type: str,
        filename: str = "audio.mp3",
    ) -> str:
        """提交音频给 Qwen-ASR 并返回识别文本；失败抛 AsrError。

        ``filename`` 仅为保持调用方签名，不参与请求（也不写入日志）。
        """
        if not self.configured:
            logger.warning("asr not configured: missing ASR_API_KEY or ASR_BASE_URL")
            raise AsrError(
                "语音识别服务未配置，请联系管理员",
                status_code=502,
                code="ASR_NOT_CONFIGURED",
            )

        mediatype = content_type if content_type.startswith("audio/") else "audio/mpeg"
        data_url = "data:%s;base64,%s" % (
            mediatype,
            base64.b64encode(file_bytes).decode("ascii"),
        )

        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
        )

        started = time.monotonic()
        try:
            resp = self._get_client().chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": data_url},
                            }
                        ],
                    }
                ],
                stream=False,
            )
        except APITimeoutError:
            logger.warning(
                "asr timeout model=%s elapsed_ms=%d",
                self._model,
                int((time.monotonic() - started) * 1000),
            )
            raise AsrError(
                "语音识别超时，请重试", status_code=504, code="ASR_TIMEOUT"
            ) from None
        except APIConnectionError:
            logger.warning("asr connection error model=%s", self._model)
            raise AsrError(
                "语音识别服务不可用，请稍后重试",
                status_code=502,
                code="ASR_UNAVAILABLE",
            ) from None
        except APIStatusError as exc:
            # 只记录状态码，不记录供应商响应体（可能含请求信息）
            logger.warning(
                "asr upstream status=%s model=%s", exc.status_code, self._model
            )
            raise AsrError(
                "语音识别服务返回异常，请稍后重试",
                status_code=502,
                code="ASR_UPSTREAM_ERROR",
            ) from None
        except Exception as exc:  # 未知错误也不暴露细节
            logger.warning("asr unexpected error type=%s", type(exc).__name__)
            raise AsrError(
                "语音识别失败，请稍后重试",
                status_code=502,
                code="ASR_ERROR",
            ) from None

        text = self._extract_text(resp)
        if not text:
            logger.info("asr empty result model=%s", self._model)
            raise AsrError(
                "未识别到有效语音，请重试", status_code=400, code="NO_SPEECH"
            )

        logger.info(
            "asr ok model=%s elapsed_ms=%d chars=%d",
            self._model,
            int((time.monotonic() - started) * 1000),
            len(text),
        )
        return text

    @staticmethod
    def _extract_text(resp) -> str:
        """从 Chat Completions 响应中取转写文本；结构异常时返回空串。"""
        choices = getattr(resp, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if not isinstance(content, str):
            return ""
        return content.strip()
