"""自律事项 AI 解析接口。

- 必须登录：避免匿名调用大模型、控制成本；
- 按用户限流；
- 服务端只返回结构化事项，不存储用户原文与解析结果；
- 模型不可用时返回本地规则结果，并在 source 中标注。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import rate_limit
from .auth_deps import AuthContext, get_auth_context
from .errors import ApiError
from .selfdiscipline_parser import (
    MAX_TEXT,
    SelfDisciplineParser,
    local_time_context,
)

router = APIRouter(prefix="/api/selfdiscipline", tags=["自律事项"])

_RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

_parser: SelfDisciplineParser | None = None


def get_parser() -> SelfDisciplineParser:
    global _parser
    if _parser is None:
        _parser = SelfDisciplineParser()
    return _parser


class ParseItemsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    today: str | None = Field(default=None, max_length=10)
    weekday: int | None = Field(default=None, ge=1, le=7)
    now: str | None = Field(default=None, max_length=5)
    timezone: str | None = Field(default=None, max_length=64)
    client_request_id: str | None = Field(default=None, max_length=64)


def _resolve_context(payload: ParseItemsRequest):
    today, weekday, now = local_time_context(payload.timezone or "")
    if payload.today and _RE_DATE.fullmatch(payload.today):
        try:
            from datetime import date

            today = date.fromisoformat(payload.today)
        except ValueError:
            pass
    if payload.weekday:
        weekday = payload.weekday
    if payload.now and _RE_HHMM.fullmatch(payload.now):
        now = payload.now
    return today, weekday, now


@router.post("/parse-items")
def parse_items(
    payload: ParseItemsRequest,
    ctx: AuthContext = Depends(get_auth_context),
    parser: SelfDisciplineParser = Depends(get_parser),
):
    text = payload.text.strip()
    if not text:
        raise ApiError(422, "VALIDATION_ERROR", "请先写下要整理的内容")

    user_id = str(ctx.user.get("id") or "")
    allowed, retry_after = rate_limit.check_selfdiscipline_parse(user_id)
    if not allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            f"整理得太频繁了，请 {retry_after} 秒后再试",
            headers={"Retry-After": str(retry_after)},
        )
    rate_limit.record_selfdiscipline_parse(user_id)

    today, weekday, now = _resolve_context(payload)
    result = parser.parse(
        text,
        today=today,
        weekday=weekday,
        now=now,
        timezone=payload.timezone or "Asia/Shanghai",
    )

    # 非创建意图（取消/闲聊/追问）也返回 200：前端把它当成一条助手回复，
    # 不要显示成错误，更不能把“不用了”写进待办。
    return {
        "items": result.items,
        "reply": result.reply,
        "source": result.source,
        "intent": result.intent,
    }
