"""FastAPI 服务：问答接口 + 学生认证 + 聊天历史。"""

from __future__ import annotations

import logging
import sqlite3
import time
import os  # 👈 用于创建静态目录

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # 👈 用于放行生成的语音文件
from pydantic import BaseModel, Field, field_validator

from . import chat_service, speech
from .attachment_api import router as attachment_router
from .auth_api import router as auth_router
from .auth_deps import AuthContext, get_db, get_optional_auth_context
from .chat_api import router as chat_router
from .errors import ApiError, install_error_handlers
from .generator import QwenGenerator
from .graph import load_full_graph
from .loader import load_nodes
from .pipeline import run_qa, split_generated_answer
from .settings import qa_match_scope
from .subgraph import OUT_PATH, RAW_PATH
from .video_api import router as video_router
from .tts_api import router as tts_router  # 👈 引入 TTS 路由

logger = logging.getLogger("ikgr.chat")

app = FastAPI(title="中小学教材知识图谱智能问答系统")

def patch_database():
    """自动扫描并修复数据库：补全缺失的表和字段"""
    import glob
    db_files = glob.glob("**/*.db", recursive=True)
    for db in db_files:
        try:
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            
            # 1. 修复 users 表缺列 (avatar)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(users)")
                cols = [row[1] for row in cursor.fetchall()]
                if 'avatar' not in cols:
                    cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
                    print(f"✅ 自动修复：已为 {db} 的 users 表补充 avatar 列")

            # 2. 创建缺失的 attachments 表（用于存图片/PDF）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    conversation_id TEXT,
                    message_id TEXT,
                    user_message_id TEXT,
                    assistant_message_id TEXT,
                    original_name TEXT,
                    media_type TEXT,
                    byte_size INTEGER,
                    ocr_status TEXT,
                    ocr_text TEXT,
                    question_text TEXT,
                    error_code TEXT,
                    page_count INTEGER,
                    failed_pages TEXT,
                    ocr_confidence REAL,
                    file_path TEXT,
                    created_at TEXT
                )
            """)

            # 3. 如果 attachments 表已经存在，检查并补全缺失的列
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attachments'")
            if cursor.fetchone():
                cursor.execute("PRAGMA table_info(attachments)")
                att_cols = [row[1] for row in cursor.fetchall()]
                
                if 'user_message_id' not in att_cols:
                    cursor.execute("ALTER TABLE attachments ADD COLUMN user_message_id TEXT")
                    print(f"✅ 自动修复：已为 {db} 的 attachments 表补充 user_message_id 列")
                    
                if 'assistant_message_id' not in att_cols:
                    cursor.execute("ALTER TABLE attachments ADD COLUMN assistant_message_id TEXT")
                    print(f"✅ 自动修复：已为 {db} 的 attachments 表补充 assistant_message_id 列")

            conn.commit()
            conn.close()
            print(f"✅ 数据库 {db} 检查/修复完毕")
        except Exception as e:
            print(f"自动修复数据库失败 {db}: {e}")

# 👈 确保 static 目录存在，防止 StaticFiles 挂载报错
os.makedirs("static", exist_ok=True)
# 挂载静态文件目录，让前端能通过 URL 访问到生成的 MP3
app.mount("/static", StaticFiles(directory="static"), name="static")

# 统一错误结构 + X-Request-ID；认证/聊天历史路由在下面注册。
install_error_handlers(app)
app.include_router(auth_router)
app.include_router(attachment_router)
app.include_router(chat_router)
app.include_router(video_router)
app.include_router(tts_router)  # 👈 注册 TTS 路由

# CORS：App 端 uni.request 不受同源限制，但 H5 调试需要放开跨域。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_store_api(request: Request, call_next):
    """API 响应禁止浏览器/代理缓存。"""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

# 启动时加载图谱、知识点与生成器
graph = load_full_graph()
match_scope = qa_match_scope()
# full：全量数学图谱；book_5b：仅五年级下册子图（旧行为）
kp_nodes = load_nodes(OUT_PATH if match_scope == "book_5b" else RAW_PATH)
logger.info(
    "qa match scope=%s candidates=%d",
    match_scope,
    sum(1 for n in kp_nodes if n.label in ("Concept", "Skill")),
)
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
    """调用生成器填充 answer / exercises；拒答问题不发请求。"""
    if result["refused"]:
        result.setdefault("exercises", [])
        return
    try:
        raw = generator.generate(result["prompt"])
    except Exception as exc:
        logger.exception("answer generation failed type=%s", type(exc).__name__)
        raise ApiError(
            502,
            "UPSTREAM_ERROR",
            "回答生成失败，请稍后重试",
        ) from None
    if not isinstance(raw, str) or not raw.strip():
        raise ApiError(502, "UPSTREAM_ERROR", "回答生成失败，请稍后重试")

    answer, exercises = split_generated_answer(raw)
    result["answer"] = answer
    result["exercises"] = exercises
    # 持久化只写 learning_path_json，把生成结果一并放进去，历史消息可直接还原。
    if result.get("learning_path") is not None:
        result["learning_path"]["exercises"] = exercises


def _body_graph_version_id(versions: dict) -> str | None:
    """记录实际参与匹配的图谱版本。"""
    if qa_match_scope() == "book_5b":
        return versions.get("book_version_id")
    return versions.get("full_version_id") or versions.get("book_version_id")


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
        graph_version_id=_body_graph_version_id(versions),
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
    """问答。"""
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
                existing_user, existing_assistant, conn
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
                    existing_user, existing_assistant, conn
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
        graph_version_id=_body_graph_version_id(versions),
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
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 首版 5MB 上限

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
    """语音转文字。"""
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


# ===== 知识点详情 =====
@app.get("/api/knowledge/{node_id}", summary="获取知识点详情")
def get_knowledge_detail(
    node_id: str,
    ctx: AuthContext | None = Depends(get_optional_auth_context),
):
    """返回知识点的定义、例子、关联练习和前后置关系。"""
    node = None
    for n in kp_nodes:
        if n.id == node_id:
            node = n
            break
    
    if node is None:
        raise ApiError(404, "NODE_NOT_FOUND", "知识点不存在")
    
    props = node.properties or {}
    
    related_exercises = []
    from .loader import load_edges
    edges = load_edges(OUT_PATH if match_scope == "book_5b" else RAW_PATH)
    
    for e in edges:
        if e.target == node_id and e.type == "tests_concept":
            for ex in kp_nodes:
                if ex.id == e.source and ex.label == "Exercise":
                    ex_props = ex.properties or {}
                    related_exercises.append({
                        "id": ex.id,
                        "name": ex.name,
                        "stem": ex_props.get("stem", ex.name),
                        "answer": ex_props.get("answer", ""),
                        "difficulty": ex_props.get("difficulty", 1),
                        "analysis": ex_props.get("analysis", ""),
                    })
        elif e.source == node_id and e.type == "tests_skill":
            for ex in kp_nodes:
                if ex.id == e.target and ex.label == "Exercise":
                    ex_props = ex.properties or {}
                    related_exercises.append({
                        "id": ex.id,
                        "name": ex.name,
                        "stem": ex_props.get("stem", ex.name),
                        "answer": ex_props.get("answer", ""),
                        "difficulty": ex_props.get("difficulty", 1),
                        "analysis": ex_props.get("analysis", ""),
                    })
    
    prerequisites = []
    successors = []
    for e in edges:
        if e.target == node_id and e.type == "prerequisites_for":
            for pn in kp_nodes:
                if pn.id == e.source:
                    prerequisites.append({"id": pn.id, "name": pn.name, "label": pn.label})
        elif e.source == node_id and e.type == "prerequisites_for":
            for sn in kp_nodes:
                if sn.id == e.target:
                    successors.append({"id": sn.id, "name": sn.name, "label": sn.label})
    
    return {
        "id": node.id,
        "label": node.label,
        "name": node.name,
        "definition": props.get("definition") or props.get("description", ""),
        "importance": props.get("importance", ""),
        "pages": props.get("pages", ""),
        "examples": props.get("examples", []),
        "exercises": related_exercises[:5],
        "prerequisites": prerequisites,
        "successors": successors,
    }


# ==================== 智能答案校验 API ====================
class CheckAnswerRequest(BaseModel):
    """答案校验请求"""
    question: str = Field(..., description="题目内容")
    user_answer: str = Field(..., description="学生答案")
    correct_answer: str = Field(..., description="参考答案")
    question_type: str = Field(default="fill", description="题目类型: choice/fill")


@app.post("/api/check-answer")
def check_answer(req: CheckAnswerRequest):
    """使用 LLM 智能校验学生答案是否正确。"""
    prompt = f"""你是一个专业的数学老师，负责批改学生的作业答案。

【题目】{req.question}

【参考答案】{req.correct_answer}

【学生答案】{req.user_answer}

请判断学生的答案是否正确。注意：
1. 如果学生答案的核心意思与参考答案一致，应该判为正确
2. 对于数学计算题，只要最终数值正确，即使过程简略也应判对
3. 对于填空题，学生答案包含关键信息即可
4. 不要过于严格，要考虑学生的表达方式可能不同

请严格按以下 JSON 格式返回（不要包含其他内容）：
{{"is_correct": true/false, "confidence": 0.0-1.0的数值, "feedback": "简短的反馈信息"}}"""

    try:
        raw_response = generator.generate(prompt)
        import json
        import re

        json_match = re.search(r'\{[^{}]*"is_correct"[^{}]*\}', raw_response)
        if json_match:
            result = json.loads(json_match.group())
        else:
            user_clean = req.user_answer.strip().lower()
            correct_clean = req.correct_answer.strip().lower()
            is_correct = bool(user_clean and correct_clean and (
                user_clean in correct_clean or
                correct_clean in user_clean or
                user_clean.replace(" ", "") in correct_clean.replace(" ", "")
            ))
            result = {
                "is_correct": is_correct,
                "confidence": 0.7 if is_correct else 0.3,
                "feedback": "答案基本正确" if is_correct else "答案不准确，请再想想"
            }

        return {
            "success": True,
            "data": {
                "is_correct": result.get("is_correct", False),
                "confidence": result.get("confidence", 0.5),
                "feedback": result.get("feedback", "已批改")
            }
        }

    except Exception as exc:
        logger.exception("answer check failed: %s", exc)
        user_clean = req.user_answer.strip().lower()
        correct_clean = req.correct_answer.strip().lower()
        is_correct = bool(
            user_clean and correct_clean and
            (user_clean in correct_clean or correct_clean in user_clean)
        )
        return {
            "success": True,
            "data": {
                "is_correct": is_correct,
                "confidence": 0.6,
                "feedback": "答案" + ("正确" if is_correct else "不准确")
            }
        }