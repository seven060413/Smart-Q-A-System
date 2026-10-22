"""Qwen 在线生成（阿里云 DashScope，OpenAI 兼容协议）。"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 从项目根目录 .env 读取密钥与模型配置
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class QwenGenerator:
    """调用 Qwen 在线接口生成讲解文本。"""

    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(
            api_key=os.getenv("QWEN_API_KEY"),
            base_url=os.getenv("QWEN_BASE_URL"),
        )
        self._model = os.getenv("QWEN_MODEL", "qwen-plus")

    def generate(self, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
        return resp.choices[0].message.content
