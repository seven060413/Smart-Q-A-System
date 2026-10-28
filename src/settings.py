"""认证相关配置：全部从环境变量读取，代码里不留真实密钥。

本阶段不需要签名密钥（令牌是随机数，数据库只存哈希），因此没有新增必须配置的
secret。可调项都有安全默认值，部署时可用 .env 覆盖。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
# 复用项目根目录的 .env；override=False，不覆盖已有环境变量。
load_dotenv(ROOT / ".env")

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def auth_token_ttl_days() -> int:
    """登录令牌有效期（天），默认 30，限制在 1–365。"""
    return _int_env("AUTH_TOKEN_TTL_DAYS", 30, 1, 365)


def rate_limit_enabled() -> bool:
    """是否启用内存限流；测试或特殊环境可设为 false。"""
    raw = os.getenv("AUTH_RATE_LIMIT_ENABLED", "true").strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _FALSE_VALUES:
        return False
    return True


def register_rate_limit() -> tuple[int, int]:
    """注册限流：(次数, 窗口秒数)，默认每 IP 每小时 5 次。"""
    limit = _int_env("AUTH_REGISTER_LIMIT", 5, 1, 1000)
    window = _int_env("AUTH_REGISTER_WINDOW_SECONDS", 3600, 1, 86400)
    return limit, window


def login_rate_limit() -> tuple[int, int]:
    """登录失败限流：(次数, 窗口秒数)，默认每 IP+用户名 15 分钟 10 次。"""
    limit = _int_env("AUTH_LOGIN_FAILURE_LIMIT", 10, 1, 1000)
    window = _int_env("AUTH_LOGIN_WINDOW_SECONDS", 900, 1, 86400)
    return limit, window


def scrypt_n() -> int:
    """scrypt 的 CPU/内存成本参数；默认 2^15，测试可临时调低。"""
    return _int_env("AUTH_SCRYPT_N", 32768, 1024, 1048576)
