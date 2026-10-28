"""统一 API 错误响应。

成功响应保持各接口原有结构；错误统一为：
    {"error": {"code", "message", "details", "request_id"}}

安全要点：
- 校验错误只返回字段位置和提示，不回显请求值，避免把密码写进响应/日志；
- 未处理异常只返回通用 500，不暴露堆栈；
- 每个响应带 X-Request-ID，便于排查。
"""

from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("ikgr.errors")


class ApiError(Exception):
    """业务错误：由全局处理器转成统一错误响应。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details=None,
        headers: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details=None,
    headers: dict | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": _request_id(request),
            }
        },
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    """注册请求 id 中间件与统一异常处理器（只调用一次）。"""

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = (
            request.headers.get("X-Request-ID") or uuid.uuid4().hex
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return _error_response(
            request,
            exc.status_code,
            exc.code,
            exc.message,
            exc.details,
            exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # 只保留 loc/msg/type，绝不回显 input（其中可能包含 password）。
        details = [
            {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", "参数不合法"),
                "type": err.get("type", "validation_error"),
            }
            for err in exc.errors()
        ]
        return _error_response(
            request, 422, "VALIDATION_ERROR", "请求参数不合法", details
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code_map = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
        }
        code = code_map.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return _error_response(
            request,
            exc.status_code,
            code,
            message,
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception(
            "Unhandled error request_id=%s type=%s",
            _request_id(request),
            type(exc).__name__,
        )
        return _error_response(
            request, 500, "INTERNAL_ERROR", "服务内部错误"
        )
