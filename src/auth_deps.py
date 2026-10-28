"""FastAPI 认证依赖：从 Bearer 令牌解析当前用户。

关键安全规则：
- 只信 Authorization 头，绝不从 query/body 读取 user_id 作为身份；
- 令牌必须存在、未撤销、未过期，且用户 status='active'；
- 无效令牌不会被降级成游客；游客只能通过“完全不携带 Authorization”进入。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import auth_service, db
from .errors import ApiError
from .security import hours_ago, now_utc, token_hash

# auto_error=False：缺少头时由我们自己返回统一 401 错误结构。
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


@dataclass
class AuthContext:
    user: dict
    session_id: str
    token_hash: str


def get_db():
    """每个请求一个 SQLite 连接；由 FastAPI 在请求结束时关闭。"""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _token_from_credentials(creds: HTTPAuthorizationCredentials | None) -> str:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "未登录或登录已失效",
            headers=_UNAUTHORIZED_HEADERS,
        )
    return creds.credentials


def get_auth_context(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn=Depends(get_db),
) -> AuthContext:
    """解析并校验当前登录会话，返回用户与会话信息。"""
    token = _token_from_credentials(creds)
    row = auth_service.fetch_session_by_token_hash(conn, token_hash(token))

    if row is None or row["revoked_at"] is not None:
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "未登录或登录已失效",
            headers=_UNAUTHORIZED_HEADERS,
        )

    now = now_utc()
    if row["expires_at"] <= now:
        raise ApiError(
            401,
            "TOKEN_EXPIRED",
            "登录已过期，请重新登录",
            headers=_UNAUTHORIZED_HEADERS,
        )

    if row["status"] != "active":
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "未登录或登录已失效",
            headers=_UNAUTHORIZED_HEADERS,
        )

    last_used = row["last_used_at"]
    if last_used is None or last_used < hours_ago(1):
        auth_service.touch_session(conn, row["session_id"], now)

    return AuthContext(
        user=auth_service.public_user_from_session_row(row),
        session_id=row["session_id"],
        token_hash=row["token_hash"],
    )


def get_current_user(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    """只返回用户信息，供后续受保护接口复用。"""
    return ctx.user


def get_optional_auth_context(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn=Depends(get_db),
) -> AuthContext | None:
    """可选认证：完全没带 Authorization 返回 None；带了但无效则 401。

    供后续 `/api/ask` 区分“游客”和“登录用户”使用；本阶段不接入问答接口。
    """
    if creds is None:
        return None
    return get_auth_context(creds=creds, conn=conn)


def get_logout_session(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn=Depends(get_db),
):
    """退出登录专用：令牌格式必须存在，但允许已过期/已撤销的会话再次调用。

    找不到令牌时返回 None，由接口直接返回 204，保证退出接口幂等且不泄露令牌状态。
    """
    token = _token_from_credentials(creds)
    return auth_service.fetch_session_for_logout(conn, token_hash(token))
