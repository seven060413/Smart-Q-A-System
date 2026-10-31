"""FastAPI 服务：问答接口 + 学生认证 + 聊天历史。"""

from __future__ import annotations

import logging
import sqlite3
import time

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from . import chat_service, speech
from .auth_api import router as auth_router
from .auth_deps import AuthContext, get_db, get_optional_auth_context
from .chat_api import router as chat_router
from .errors import ApiError, install_error_handlers
from .generator import QwenGenerator
from .graph import load_full_graph
from .loader import load_nodes
from .pipeline import run_qa
from .subgraph import OUT_PATH

logger = logging.getLogger("ikgr.chat")

app = FastAPI(title="中小学教材知识图谱智能问答系统")

# 统一错误结构 + X-Request-ID；认证/聊天历史路由在下面注册。
install_error_handlers(app)
app.include_router(auth_router)
app.include_router(chat_router)

# CORS：App 端 uni.request 不受同源限制，但 H5 调试需要放开跨域。
# 阶段 2.5（HTTPS/反向代理）会把这里收紧为白名单；当前保持现状以兼容旧前端。

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动时加载图谱、知识点与生成器
graph = load_full_graph()
kp_nodes = load_nodes(OUT_PATH)
generator = QwenGenerator()
# 语音转写适配层：只读环境变量，不额外初始化大模型
transcriber = speech.SpeechTranscriber()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=64)
    client_request_id: str | None = Field(default=None, max_length=64)

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("问题不能为空")
        return value

    @field_validator("conversation_id", "client_request_id")
    @classmethod
    def _optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


def _fill_answer(result: dict) -> None:
    """调用生成器填充 answer；拒答问题不发请求。"""
    if result["refused"]:
        return
    try:
        answer = generator.generate(result["prompt"])
    except Exception as exc:
        logger.exception("answer generation failed type=%s", type(exc).__name__)
        raise ApiError(
            502,
            "UPSTREAM_ERROR",
            "回答生成失败，请稍后重试",
        ) from None
    if not isinstance(answer, str) or not answer.strip():
        raise ApiError(502, "UPSTREAM_ERROR", "回答生成失败，请稍后重试")
    result["answer"] = answer


def _fail_assistant(
    conn,
    user_id: str,
    conversation_id: str,
    user_message_id: str,
    result: dict,
    versions: dict,
    latency_ms: int,
    error: ApiError,
):
    """生成失败时仍保存一轮失败记录，便于前端展示/重试。"""
    return chat_service.insert_assistant_message(
        conn,
        user_id,
        conversation_id,
        content=None,
        status="failed",
        refused=False,
        knowledge_point=result.get("knowledge_point"),
        source=result.get("source"),
        prerequisite_gaps=result.get("prerequisite_gaps"),
        learning_path=result.get("learning_path"),
        graph_version_id=versions.get("book_version_id"),
        context_graph_version_id=versions.get("full_version_id"),
        reply_to_message_id=user_message_id,
        meta=None,
        error_code=error.code,
        error_message=error.message,
        latency_ms=latency_ms,
    )


@app.get("/")
def root():
    return {"service": "中小学教材知识图谱智能问答系统", "docs": "/docs"}


@app.post("/api/ask")
def ask(
    req: AskRequest,
    request: Request,
    auth_ctx: AuthContext | None = Depends(get_optional_auth_context),
    conn=Depends(get_db),
):
    """问答。

    - 游客：只回答，不写数据库；带 conversation_id 返回 401。
    - 登录：可自动创建会话，保存问题/回答/知识点/图谱版本；重复
      client_request_id 返回已保存结果，避免重试产生重复消息。
    """
    # 1) 游客路径：完全不落库
    if auth_ctx is None:
        if req.conversation_id:
            raise ApiError(401, "AUTH_REQUIRED", "登录后才能保存或打开会话")
        result = run_qa(req.question, graph, kp_nodes)
        result.pop("_meta", None)
        _fill_answer(result)
        result.pop("prompt", None)
        result["persisted"] = False
        return result

    user_id = auth_ctx.user["id"]

    # 2) 幂等：同一个 client_request_id 直接返回已保存的那一轮
    if req.client_request_id:
        existing_user, existing_assistant = chat_service.find_turn_by_client_request(
            conn, user_id, req.client_request_id
        )
        if existing_user is not None:
            if (
                req.conversation_id
                and existing_user["conversation_id"] != req.conversation_id
            ):
                raise ApiError(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "该请求编号已用于其他会话",
                )
            return chat_service.stored_turn_response(
                existing_user, existing_assistant
            )

    # 3) 运行检索/诊断流水线（不调用大模型，先拿到结构化证据）
    result = run_qa(req.question, graph, kp_nodes)
    meta = result.pop("_meta", None)

    # 4) 确定会话：必须属于当前用户；没有则自动创建
    if req.conversation_id:
        conv = chat_service.get_conversation(conn, user_id, req.conversation_id)
        if conv is None:
            raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")
        conversation_id = conv["id"]
    else:
        conv = chat_service.create_conversation(
            conn,
            user_id,
            title=chat_service.title_from_question(req.question),
        )
        conversation_id = conv["id"]

    # 5) 先写入用户问题（短事务），再调用生成器；失败也能留下记录
    try:
        user_msg = chat_service.insert_user_message(
            conn,
            user_id,
            conversation_id,
            req.question,
            req.client_request_id,
        )
    except sqlite3.IntegrityError:
        # 并发重试：另一个请求已经写入同一个 client_request_id
        if req.client_request_id:
            existing_user, existing_assistant = (
                chat_service.find_turn_by_client_request(
                    conn, user_id, req.client_request_id
                )
            )
            if existing_user is not None:
                return chat_service.stored_turn_response(
                    existing_user, existing_assistant
                )
        raise

    versions = chat_service.active_graph_version_ids(conn)
    started = time.monotonic()

    try:
        _fill_answer(result)
    except ApiError as error:
        latency_ms = int((time.monotonic() - started) * 1000)
        assistant_msg = _fail_assistant(
            conn,
            user_id,
            conversation_id,
            user_msg["id"],
            result,
            versions,
            latency_ms,
            error,
        )
        raise ApiError(
            502,
            "UPSTREAM_ERROR",
            error.message,
            details={
                "conversation_id": conversation_id,
                "user_message_id": user_msg["id"],
                "assistant_message_id": assistant_msg["id"],
            },
        ) from None

    latency_ms = int((time.monotonic() - started) * 1000)
    assistant_msg = chat_service.insert_assistant_message(
        conn,
        user_id,
        conversation_id,
        content=result["answer"],
        status="completed",
        refused=result["refused"],
        knowledge_point=result.get("knowledge_point"),
        source=result.get("source"),
        prerequisite_gaps=result.get("prerequisite_gaps"),
        learning_path=result.get("learning_path"),
        graph_version_id=versions.get("book_version_id"),
        context_graph_version_id=versions.get("full_version_id"),
        reply_to_message_id=user_msg["id"],
        meta=meta,
        latency_ms=latency_ms,
    )

    result.pop("prompt", None)
    result["persisted"] = True
    result["conversation_id"] = conversation_id
    result["user_message_id"] = user_msg["id"]
    result["assistant_message_id"] = assistant_msg["id"]
    result["created_at"] = assistant_msg["created_at"]
    return result


# ===== 语音转文字 =====
# 只负责把短音频变成文本，不参与检索/问答流水线，也不落盘音频。

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 首版 5MB 上限

# 可接受格式：按文件头魔数识别，不信任客户端 Content-Type / 文件名
_AUDIO_FORMATS = {
    "mp3": ("audio/mpeg", "audio.mp3"),
    "wav": ("audio/wav", "audio.wav"),
    "ogg": ("audio/ogg", "audio.ogg"),
    "webm": ("audio/webm", "audio.webm"),
    "m4a": ("audio/mp4", "audio.m4a"),
    "flac": ("audio/flac", "audio.flac"),
}


def _detect_audio_format(head: bytes) -> str | None:
    """根据文件头返回规范格式名；无法识别返回 None。"""
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:3] == b"ID3":
        return "mp3"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head[:4] == b"fLaC":
        return "flac"
    return None


@app.post("/api/transcribe")
def transcribe(file: UploadFile = File(...)):
    """语音转文字。

    - 只接受常见短音频格式且 ≤ 5MB，校验失败/空文件/超限返回 4xx；
    - 读取到内存后调用 ASR 适配层，不写临时文件，识别完即丢弃；
    - 错误统一走 ApiError，不把密钥或供应商内部信息返回客户端。
    """
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "AUDIO_TOO_LARGE", "音频文件过大，请控制在 5MB 以内")
    if not data:
        raise ApiError(400, "EMPTY_FILE", "未收到音频文件")

    fmt = _detect_audio_format(data[:16])
    if fmt is None:
        raise ApiError(400, "UNSUPPORTED_FORMAT", "不支持的音频格式，请重新录制")

    content_type, filename = _AUDIO_FORMATS[fmt]
    try:
        text = transcriber.transcribe(data, content_type, filename)
    except speech.AsrError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from None

    return {"text": text}
