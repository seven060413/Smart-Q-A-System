"""密码哈希与登录令牌工具。

密码：
- 只存 scrypt 哈希，格式 `scrypt$N$r$p$<base64盐>$<base64哈希>`；
- 每个用户独立随机盐；参数随哈希保存，便于以后提高成本而不影响旧账号；
- 校验用 hmac.compare_digest，避免计时侧信道。

令牌：
- 32 字节随机数 + `ikgr_` 前缀，只在登录/注册响应中返回一次；
- 数据库只存 SHA-256 十六进制，泄露数据库也拿不到可用令牌。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .settings import scrypt_n

SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
# scrypt 的内存上限；N=2^15, r=8 约需 32 MiB，留一倍余量。
SCRYPT_MAXMEM = 64 * 1024 * 1024
TOKEN_PREFIX = "ikgr_"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def now_utc() -> str:
    """当前 UTC 时间，格式与 API/数据库一致。"""
    return _iso(datetime.now(timezone.utc))


def expires_at(days: int) -> str:
    """从现在起 days 天后的 UTC 时间。"""
    return _iso(datetime.now(timezone.utc) + timedelta(days=days))


def hours_ago(hours: int) -> str:
    """用于判断 last_used_at 是否足够旧，避免每个请求都写库。"""
    return _iso(datetime.now(timezone.utc) - timedelta(hours=hours))


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)


def _hash_with_n(password: str, n: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"scrypt${n}${SCRYPT_R}${SCRYPT_P}${_b64e(salt)}${_b64e(digest)}"


def hash_password(password: str) -> str:
    """生成带随机盐的 scrypt 哈希字符串。"""
    return _hash_with_n(password, scrypt_n())


def verify_password(password: str, stored: str) -> bool:
    """校验密码；格式错误、参数异常或密码错误统一返回 False。"""
    try:
        algo, n_text, r_text, p_text, salt_text, digest_text = stored.split("$")
        if algo != "scrypt":
            return False
        n, r, p = int(n_text), int(r_text), int(p_text)
        # 防止数据库被篡改后传入极端参数导致 DoS。
        if not (2**10 <= n <= 2**20 and 1 <= r <= 32 and 1 <= p <= 4):
            return False
        salt = _b64d(salt_text)
        expected = _b64d(digest_text)
        if not salt or not expected:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=SCRYPT_MAXMEM,
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


@lru_cache(maxsize=8)
def _dummy_hash_for_n(n: int) -> str:
    """固定成本用的假哈希：用户不存在时也做一次等价校验，降低计时差异。"""
    return _hash_with_n(secrets.token_urlsafe(16), n)


def dummy_password_hash() -> str:
    """返回与当前 scrypt 参数匹配的假哈希，供登录失败路径使用。"""
    return _dummy_hash_for_n(scrypt_n())


def new_token() -> str:
    """生成不透明登录令牌；只在签发时返回一次。"""
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    """令牌的 SHA-256；数据库只保存该值。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
