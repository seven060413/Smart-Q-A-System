"""学生注册、登录与登录会话的数据库操作。

只处理业务与 SQL，不依赖 FastAPI；接口层在 src/auth_api.py，鉴权依赖在
src/auth_deps.py。所有函数都使用调用方传入的连接，便于测试替换数据库。
"""

from __future__ import annotations

import sqlite3
import uuid

from .errors import ApiError
from .security import (
    dummy_password_hash,
    expires_at,
    hash_password,
    new_token,
    now_utc,
    token_hash,
    verify_password,
)
from .settings import auth_token_ttl_days

# 对外可见的用户字段，绝不包含 password_hash / status。
_PUBLIC_USER_SQL = (
    "id, username, display_name, role, created_at, last_login_at"
)


def _public_user(row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
        "created_at": row["created_at"],
        "last_login_at": row["last_login_at"],
    }


def _issue_session(conn, user_id: str, user_agent: str | None) -> tuple[str, str, str]:
    """创建登录会话，返回 (明文令牌, 过期时间, session_id)。"""
    token = new_token()
    session_id = uuid.uuid4().hex
    now = now_utc()
    exp = expires_at(auth_token_ttl_days())
    conn.execute(
        "INSERT INTO auth_sessions "
        "(id, user_id, token_hash, created_at, expires_at, last_used_at, user_agent) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            user_id,
            token_hash(token),
            now,
            exp,
            now,
            (user_agent or "")[:255] or None,
        ),
    )
    return token, exp, session_id


def register_user(
    conn,
    username: str,
    password: str,
    display_name: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """创建 student 账号并自动登录。

    用户名大小写不敏感唯一由数据库 uq_users_username 保证；role 在服务端硬编码，
    不接受调用方传入。密码哈希在事务外计算，避免长时间持有写锁。
    """
    password_hash = hash_password(password)
    user_id = uuid.uuid4().hex
    now = now_utc()
    final_display_name = display_name or username

    try:
        with conn:
            conn.execute(
                "INSERT INTO users "
                "(id, username, display_name, password_hash, role, status, "
                " created_at, updated_at, last_login_at) "
                "VALUES (?, ?, ?, ?, 'student', 'active', ?, ?, ?)",
                (
                    user_id,
                    username,
                    final_display_name,
                    password_hash,
                    now,
                    now,
                    now,
                ),
            )
            token, exp, _ = _issue_session(conn, user_id, user_agent)
    except sqlite3.IntegrityError as exc:
        if "users.username" in str(exc):
            raise ApiError(409, "USERNAME_TAKEN", "用户名已被使用") from None
        raise

    return {
        "token": token,
        "token_type": "bearer",
        "expires_at": exp,
        "user": {
            "id": user_id,
            "username": username,
            "display_name": final_display_name,
            "role": "student",
            "created_at": now,
            "last_login_at": now,
        },
    }


def login_user(
    conn,
    username: str,
    password: str,
    user_agent: str | None = None,
) -> dict:
    """校验用户名/密码并签发新令牌。

    账号不存在与密码错误返回完全相同的错误，避免账号枚举；账号不存在时也执行
    一次假哈希校验，降低响应时间差异。
    """
    row = conn.execute(
        f"SELECT {_PUBLIC_USER_SQL}, password_hash, status "
        "FROM users WHERE username = ?",
        (username,),
    ).fetchone()

    if row is None:
        verify_password(password, dummy_password_hash())
        raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")

    if not verify_password(password, row["password_hash"]):
        raise ApiError(401, "INVALID_CREDENTIALS", "用户名或密码错误")

    if row["status"] != "active":
        # 只有密码正确后才会看到这个提示，不会让攻击者借此枚举账号。
        raise ApiError(403, "ACCOUNT_DISABLED", "账号已被禁用")

    now = now_utc()
    with conn:
        token, exp, _ = _issue_session(conn, row["id"], user_agent)
        conn.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (now, now, row["id"]),
        )

    return {
        "token": token,
        "token_type": "bearer",
        "expires_at": exp,
        "user": {
            "id": row["id"],
            "username": row["username"],
            "display_name": row["display_name"],
            "role": row["role"],
            "created_at": row["created_at"],
            "last_login_at": now,
        },
    }


def fetch_session_by_token_hash(conn, hashed_token: str):
    """按令牌哈希查会话与用户；不判断有效性，由依赖层统一判断。"""
    return conn.execute(
        "SELECT s.id AS session_id, s.token_hash, s.expires_at, s.revoked_at, "
        "       s.last_used_at, "
        "       u.id, u.username, u.display_name, u.role, u.status, "
        "       u.created_at, u.last_login_at "
        "FROM auth_sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ?",
        (hashed_token,),
    ).fetchone()


def fetch_session_for_logout(conn, hashed_token: str):
    """退出登录用：只按令牌哈希找会话，允许已过期/已撤销的会话再次调用。"""
    return conn.execute(
        "SELECT id AS session_id, revoked_at FROM auth_sessions WHERE token_hash = ?",
        (hashed_token,),
    ).fetchone()


def touch_session(conn, session_id: str, now: str) -> None:
    """低频更新 last_used_at（依赖层控制频率）。"""
    with conn:
        conn.execute(
            "UPDATE auth_sessions SET last_used_at = ? WHERE id = ?",
            (now, session_id),
        )


def revoke_session(conn, session_id: str) -> None:
    """撤销指定会话；已撤销时是幂等的 no-op。"""
    with conn:
        conn.execute(
            "UPDATE auth_sessions SET revoked_at = ? "
            "WHERE id = ? AND revoked_at IS NULL",
            (now_utc(), session_id),
        )


def public_user_from_session_row(row) -> dict:
    """把 fetch_session_by_token_hash 的行转成公开用户字段。"""
    return _public_user(row)
