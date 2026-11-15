"""Qwen-OCR adapter through Alibaba Cloud Model Studio's OpenAI-compatible API."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from dotenv import load_dotenv

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-vl-ocr"
MAX_OCR_TEXT = 4000


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float | None


class OCRAdapter:
    def recognize(self, data: bytes, media_type: str) -> OCRResult:
        raise NotImplementedError


class DisabledOCR(OCRAdapter):
    def recognize(self, data: bytes, media_type: str) -> OCRResult:
        raise RuntimeError("OCR provider is not configured")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith("你的") or value.startswith("sk-你的"):
        raise RuntimeError(f"{name} is not configured")
    return value


def _data_url(data: bytes, media_type: str) -> str:
    if media_type not in {"image/jpeg", "image/png"}:
        raise ValueError("unsupported image media type")
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
            value = item.get("text") or item.get("content")
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts).strip()


def parse_response(response) -> OCRResult:
    """Parse only the public text content; never expose provider response details."""
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise RuntimeError("OCR response has no choices")
    message = getattr(choices[0], "message", None)
    text = _content_text(getattr(message, "content", None))
    if not text:
        raise RuntimeError("OCR returned empty text")
    confidence = None
    raw_confidence = getattr(response, "confidence", None)
    if isinstance(raw_confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(raw_confidence)))
    return OCRResult(text=text[:MAX_OCR_TEXT], confidence=confidence)


class QwenOCRAdapter(OCRAdapter):
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, model: str | None = None, timeout: float = 30.0):
        self._api_key = (api_key or os.getenv("DASHSCOPE_API_KEY", "")).strip()
        self._base_url = (base_url or os.getenv("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL)).strip() or DEFAULT_BASE_URL
        self._model = (model or os.getenv("OCR_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        self._timeout = max(1.0, min(float(timeout), 60.0))
        if not self._api_key or self._api_key.startswith("你的") or self._api_key.startswith("sk-你的"):
            raise RuntimeError("DASHSCOPE_API_KEY is not configured")

    def recognize(self, data: bytes, media_type: str) -> OCRResult:
        if not data:
            raise ValueError("image data is empty")
        try:
            from openai import APITimeoutError, OpenAI
            client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout)
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": _data_url(data, media_type)}},
                            {
                                "type": "text",
                                "text": "请只提取图片中的数学题文字和公式，保持原有顺序，不要解题，不要添加说明。",
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            )
            return parse_response(response)
        except (TimeoutError, APITimeoutError, ConnectionError):
            raise TimeoutError("OCR request timed out") from None
        except RuntimeError:
            raise
        except Exception as exc:
            # Do not return provider messages: they may contain request metadata or secrets.
            raise RuntimeError("OCR provider request failed") from exc


def get_ocr_adapter() -> OCRAdapter:
    if provider_name() == "qwen_ocr":
        return QwenOCRAdapter()
    return DisabledOCR()


def provider_name() -> str:
    return os.getenv("OCR_PROVIDER", "none").strip().lower() or "none"
