"""学情诊断 API：目录、会话、结果、错题、图谱与趋势。

- GET  /api/diagnose/catalog                      年级 / 册 / 章 / 知识点目录
- POST /api/diagnose/quiz                         action=start | answer | abort
- GET  /api/diagnose/sessions/latest              最近一次完成结果
- GET  /api/diagnose/sessions                     会话历史（需登录）
- GET  /api/diagnose/sessions/{session_id}        单次结果 / 未完成会话
- GET  /api/diagnose/wrong-questions              错题集（需登录）
- POST /api/diagnose/wrong-questions/{id}/mark    标记错题状态
- GET  /api/diagnose/graph                        错题知识图谱
- GET  /api/diagnose/trends                       学情趋势（需登录）

设计要点：
- 正确答案只存在服务端，作答前响应里没有 answer；
- 游客可诊断（匿名会话），登录用户的会话绑定 user_id；
- 历史 / 错题 / 趋势必须登录，游客会话凭 session_id 读取；
- 同一 client_request_id 重试返回首次结果，避免网络重试重复推进。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field

from . import quiz_service
from .auth_deps import (
    AuthContext,
    get_auth_context,
    get_db,
    get_optional_auth_context,
)
from .errors import ApiError

router = APIRouter()


class QuizRequest(BaseModel):
    action: str = Field(default="start", description="start | answer | abort")
    mode: str | None = Field(default=None, description="single | chapter | grade")
    node_ids: list[str] | None = Field(default=None, max_length=500)
    grade: int | None = Field(default=None, ge=1, le=14)
    semester: str | None = Field(default="all", max_length=8)
    max_questions: int | None = Field(default=None, ge=1, le=100)
    mastery_streak: int | None = Field(default=None)
    session_id: str | None = Field(default=None, max_length=64)
    question_id: str | None = Field(default=None, max_length=64)
    answer: str | None = Field(default=None, max_length=500)
    client_request_id: str | None = Field(default=None, max_length=64)


@router.get("/api/diagnose/catalog", summary="学情诊断目录")
def diagnosis_catalog():
    return quiz_service.get_catalog()


class MarkWrongRequest(BaseModel):
    status: str = Field(description="open | mastered | ignored")


@router.get("/api/diagnose/sessions/latest", summary="最近一次诊断结果")
def diagnosis_latest(
    auth_ctx: AuthContext | None = Depends(get_optional_auth_context),
    conn=Depends(get_db),
):
    # 游客不保存历史；前端用本地 session_id 调单次结果接口。
    if auth_ctx is None:
        raise ApiError(404, "SESSION_NOT_FOUND", "没有可恢复的诊断记录")
    item = quiz_service.latest_session(conn, auth_ctx.user["id"])
    if item is None:
        return Response(status_code=204)
    return item


@router.get("/api/diagnose/sessions", summary="诊断会话历史")
def diagnosis_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
    grade: int | None = Query(default=None, ge=1, le=14),
    auth_ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    return quiz_service.list_sessions(
        conn, auth_ctx.user["id"], limit=limit, cursor=cursor, grade=grade
    )


@router.get("/api/diagnose/sessions/{session_id}", summary="单次诊断结果")
def diagnosis_session(
    session_id: str,
    auth_ctx: AuthContext | None = Depends(get_optional_auth_context),
    conn=Depends(get_db),
):
    return quiz_service.get_session(conn, auth_ctx, session_id)


@router.get("/api/diagnose/wrong-questions", summary="错题集")
def diagnosis_wrong_questions(
    grade: int | None = Query(default=None, ge=1, le=14),
    chapter: str | None = Query(default=None, max_length=200),
    node_key: str | None = Query(default=None, max_length=64),
    status: str = Query(default="open", max_length=16),
    days: int | None = Query(default=None, ge=1, le=3650),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=200),
    auth_ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    return quiz_service.list_wrong_questions(
        conn,
        auth_ctx.user["id"],
        grade=grade,
        chapter=chapter,
        node_key=node_key,
        status=status,
        days=days,
        limit=limit,
        cursor=cursor,
    )


@router.post("/api/diagnose/wrong-questions/{attempt_id}/mark", summary="标记错题")
def diagnosis_mark_wrong(
    attempt_id: int,
    req: MarkWrongRequest,
    auth_ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    return quiz_service.mark_wrong_question(
        conn, auth_ctx.user["id"], attempt_id, req.status
    )


@router.get("/api/diagnose/graph", summary="错题知识图谱")
def diagnosis_graph(
    session_id: str | None = Query(default=None, max_length=64),
    node_keys: str | None = Query(default=None, max_length=4000),
    depth: int = Query(default=2, ge=1, le=3),
    auth_ctx: AuthContext | None = Depends(get_optional_auth_context),
    conn=Depends(get_db),
):
    seeds = [part.strip() for part in (node_keys or "").split(",") if part.strip()]
    return quiz_service.graph_payload(
        conn,
        auth_ctx,
        session_id=session_id or None,
        node_keys=seeds,
        depth=depth,
    )


@router.get("/api/diagnose/trends", summary="学情趋势")
def diagnosis_trends(
    grade: int | None = Query(default=None, ge=1, le=14),
    limit: int = Query(default=10, ge=2, le=100),
    date_from: str | None = Query(default=None, alias="from", max_length=40),
    date_to: str | None = Query(default=None, alias="to", max_length=40),
    auth_ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    return quiz_service.build_trends(
        conn,
        auth_ctx.user["id"],
        grade=grade,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/api/diagnose/quiz", summary="学情诊断会话")
def diagnosis_quiz(
    req: QuizRequest,
    auth_ctx: AuthContext | None = Depends(get_optional_auth_context),
    conn=Depends(get_db),
):
    payload = req.model_dump(exclude_none=True)
    action = payload.pop("action", "start")

    if action == "start":
        if not payload.get("mode"):
            raise ApiError(400, "MISSING_MODE", "开始诊断需要 mode")
        return quiz_service.create_session(conn, auth_ctx, payload)
    if action == "answer":
        if not payload.get("session_id") or not payload.get("question_id"):
            raise ApiError(400, "MISSING_FIELD", "作答需要 session_id 和 question_id")
        return quiz_service.answer_session(conn, auth_ctx, payload)
    if action == "abort":
        if not payload.get("session_id"):
            raise ApiError(400, "MISSING_FIELD", "中止需要 session_id")
        return quiz_service.abort_session(conn, auth_ctx, payload)
    raise ApiError(400, "INVALID_ACTION", "action 只能是 start / answer / abort")
