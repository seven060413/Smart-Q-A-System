"""学生认证接口：注册、登录、当前用户、退出。

接口前缀 `/api/auth`；本文件不实现前端页面，也不实现聊天历史接口。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import auth_service, rate_limit
from .auth_deps import (
    AuthContext,
    get_auth_context,
    get_db,
    get_logout_session,
)
from .errors import ApiError

router = APIRouter(prefix="/api/auth", tags=["认证"])

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")


def _validate_username(value: str) -> str:
    value = value.strip()
    if not _USERNAME_RE.fullmatch(value):
        raise ValueError("用户名需为 3-32 位字母、数字或下划线")
    return value


def _validate_login_password(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("密码不能为空")
    if len(value) > 128:
        raise ValueError("密码长度不能超过 128 位")
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = None

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return _validate_username(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("密码不能全为空白字符")
        return value

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 32:
            raise ValueError("展示名不能超过 32 个字符")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("展示名不能包含控制字符")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        return _validate_username(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _validate_login_password(value)


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    created_at: str
    last_login_at: str | None = None


class TokenOut(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserOut


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _user_agent(request: Request) -> str | None:
    raw = request.headers.get("user-agent")
    return raw[:255] if raw else None


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=201,
    summary="学生注册（自动登录）",
)
def register(
    req: RegisterRequest,
    request: Request,
    conn=Depends(get_db),
):
    """创建 student 账号并返回登录令牌。

    服务端硬编码 role='student'；老师/管理员账号只能由后台脚本创建。
    """
    ip = _client_ip(request)
    allowed, retry_after = rate_limit.check_register(ip)
    if not allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "注册过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
    rate_limit.record_register(ip)

    return auth_service.register_user(
        conn,
        req.username,
        req.password,
        req.display_name,
        _user_agent(request),
    )


@router.post("/login", response_model=TokenOut, summary="学生登录")
def login(
    req: LoginRequest,
    request: Request,
    conn=Depends(get_db),
):
    """校验用户名/密码并签发新令牌；失败信息统一，不区分账号是否存在。"""
    ip = _client_ip(request)
    allowed, retry_after = rate_limit.check_login(ip, req.username)
    if not allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "登录尝试过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        result = auth_service.login_user(
            conn,
            req.username,
            req.password,
            _user_agent(request),
        )
    except ApiError as exc:
        if exc.status_code in (401, 403):
            rate_limit.record_login_failure(ip, req.username)
        raise

    rate_limit.clear_login(ip, req.username)
    return result


@router.get("/me", response_model=UserOut, summary="当前登录用户")
def me(ctx: AuthContext = Depends(get_auth_context)):
    """只根据 Bearer 令牌返回用户；请求里的 user_id 等字段一律不参与身份判断。"""
    return ctx.user


@router.post("/logout", status_code=204, summary="退出当前设备")
def logout(
    session=Depends(get_logout_session),
    conn=Depends(get_db),
):
    """撤销当前令牌；重复调用返回 204，不泄露令牌是否曾经有效。"""
    if session is not None:
        auth_service.revoke_session(conn, session["session_id"])
    return Response(status_code=204)
