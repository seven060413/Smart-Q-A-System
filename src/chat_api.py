"""聊天历史接口：会话列表、创建、详情、消息分页、软删除。

所有接口都要求 Bearer 登录；用户身份只来自 auth 依赖，绝不读取请求里的 user_id。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from . import chat_service
from .auth_deps import AuthContext, get_auth_context, get_db
from .errors import ApiError

router = APIRouter(prefix="/api", tags=["聊天历史"])


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=80)
    course_id: str = Field(default="math", min_length=1, max_length=32)


@router.get("/conversations", summary="当前学生的会话列表")
def list_conversations(
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(default=None),
    ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    return chat_service.list_conversations(
        conn, ctx.user["id"], limit=limit, cursor=cursor
    )


@router.post("/conversations", status_code=201, summary="创建会话")
def create_conversation(
    req: CreateConversationRequest,
    ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    return chat_service.create_conversation(
        conn,
        ctx.user["id"],
        title=req.title,
        course_id=req.course_id,
    )


@router.get("/conversations/{conversation_id}", summary="会话详情")
def get_conversation(
    conversation_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    conv = chat_service.get_conversation(conn, ctx.user["id"], conversation_id)
    if conv is None:
        raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")
    return conv


@router.get("/conversations/{conversation_id}/messages", summary="会话消息分页")
def list_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    conv = chat_service.get_conversation(conn, ctx.user["id"], conversation_id)
    if conv is None:
        raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")
    return chat_service.list_messages(
        conn, conversation_id, limit=limit, cursor=cursor
    )


@router.delete("/conversations/{conversation_id}", status_code=204, summary="软删除会话")
def delete_conversation(
    conversation_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    result = chat_service.soft_delete_conversation(
        conn, ctx.user["id"], conversation_id
    )
    if result is None:
        raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")
    return Response(status_code=204)
