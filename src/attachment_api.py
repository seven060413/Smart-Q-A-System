"""Authenticated single-image question MVP endpoints."""

from __future__ import annotations

import json
import logging
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from . import attachment_service, chat_service, pdf_service
from .db import connect
from .auth_deps import AuthContext, get_auth_context, get_db
from .errors import ApiError
from .generator import QwenGenerator
from .graph import load_full_graph
from .linking import link_entity
from .loader import load_nodes
from .ocr import get_ocr_adapter
from .pipeline import run_qa, split_generated_answer
from .settings import qa_match_scope
from .subgraph import OUT_PATH, RAW_PATH
from .security import now_utc

logger = logging.getLogger("ikgr.attachments")
router = APIRouter(prefix="/api/attachments", tags=["attachments"])
_graph = load_full_graph()
_nodes = load_nodes(OUT_PATH if qa_match_scope() == "book_5b" else RAW_PATH)
_generator = QwenGenerator()
_pdf_executor = ThreadPoolExecutor(max_workers=pdf_service.MAX_ACTIVE_DOCUMENTS, thread_name_prefix="pdf-job")
_pdf_jobs_lock = threading.Lock()
_pdf_jobs: set[str] = set()


# 解题文本上限：多页 PDF 的 OCR 拼接文本可达成倍于单题的长度（每页上限 4000 字），
# 请求侧放宽到 20000 字避免"后端自己生成的文本被自己的校验拒绝"；
# 超限在 validator 里给中文提示（Field(max_length) 会先触发并返回英文信息）。
MAX_SOLVE_TEXT = 20000


class AttachmentSolveRequest(BaseModel):
    text: str = Field(min_length=1)
    conversation_id: str | None = Field(default=None, max_length=64)
    knowledge_point_id: str | None = Field(default=None, max_length=128)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("题目文本不能为空")
        if len(value) > MAX_SOLVE_TEXT:
            raise ValueError(f"题目文本不能超过 {MAX_SOLVE_TEXT} 字（当前 {len(value)} 字），请编辑后再试")
        return value


def _conversation(conn, user_id: str, conversation_id: str | None) -> str | None:
    if not conversation_id:
        return None
    row = chat_service.get_conversation(conn, user_id, conversation_id)
    if row is None:
        raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")
    return row["id"]


def _clean_question_text(text: str) -> str:
    """Remove OCR LaTeX wrapper noise while preserving the mathematical wording."""
    value = re.sub(r"\\(?:subsection|section|text|mathrm|frac|times|cdot)\b", " ", text or "")
    value = value.replace("```", " ").replace("{", " ").replace("}", " ")
    value = re.sub(r"\\+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:MAX_SOLVE_TEXT]


def _fallback_exercises(knowledge_point: str) -> list[str]:
    return [
        f"请再做一道与“{knowledge_point}”相关的基础题，并写出计算步骤。",
        f"请设计一道“{knowledge_point}”的生活应用题，并写出答案。",
    ]


def _parse_attachment_answer(raw: str, knowledge_point: str) -> tuple[str, list[str], str, str, list[dict]]:
    text = (raw or "").strip()
    # 兼容模型可能返回的括号包裹 JSON，如 ({"steps":[...],"final_answer":"..."})
    json_text = text[1:-1] if (text.startswith("(") and text.endswith(")")) else text
    try:
        payload = json.loads(json_text)
        steps = payload.get("steps") if isinstance(payload, dict) else None
        final = payload.get("final_answer") if isinstance(payload, dict) else None
        exercises = payload.get("exercises") if isinstance(payload, dict) else None
        if isinstance(steps, list) and isinstance(final, str) and isinstance(exercises, list):
            normalized_steps = []
            for i, item in enumerate(steps):
                title = str(item.get("title") or f"第 {i + 1} 步") if isinstance(item, dict) else f"第 {i + 1} 步"
                content = str(item.get("content") or "").strip() if isinstance(item, dict) else str(item).strip()
                if content:
                    normalized_steps.append({"title": title, "content": content})
            steps_text = "\n".join(f"{i + 1}. {step['title']}：{step['content']}" for i, step in enumerate(normalized_steps))
            exercise_text = [str(item.get("question", item) if isinstance(item, dict) else item).strip() for item in exercises]
            exercise_text = [item for item in exercise_text if item]
            if len(exercise_text) < 2:
                exercise_text.extend(_fallback_exercises(knowledge_point)[len(exercise_text):])
            return steps_text, exercise_text[:2], final.strip(), text, normalized_steps
    except (ValueError, TypeError, AttributeError):
        pass
    answer, exercises = split_generated_answer(text)
    if len(exercises) < 2:
        exercises.extend(_fallback_exercises(knowledge_point)[len(exercises):])
    normalized_steps = [{"title": f"第 {i + 1} 步", "content": line.strip()} for i, line in enumerate(answer.splitlines()) if line.strip()]
    return answer, exercises[:2], "", text, normalized_steps


def _solve(text: str, knowledge_point_id: str | None = None) -> dict:
    text = _clean_question_text(text)
    hits = link_entity(text, _nodes, top_k=3)
    candidates = [{"id": node.id, "name": node.name, "confidence": round(float(score), 4)} for node, score in hits]
    if knowledge_point_id:
        selected = next((node for node in _nodes if node.id == knowledge_point_id and node.label in ("Concept", "Skill")), None)
        if selected is None:
            raise ApiError(400, "INVALID_KNOWLEDGE_POINT", "所选知识点无效")
        text = f"{text}\n知识点：{selected.name}"
    result = run_qa(text, _graph, _nodes)
    if knowledge_point_id:
        result["knowledge_point"] = selected.name
        result["refused"] = False
        result["requires_confirmation"] = False
        candidates = [{"id": selected.id, "name": selected.name, "confidence": 1.0}]
    score = candidates[0]["confidence"] if candidates else 0.0
    result["knowledge_confidence"] = score
    result["knowledge_candidates"] = candidates
    result["requires_confirmation"] = score < 0.5
    if result.get("refused"):
        result["coverage_note"] = "知识图谱未可靠匹配到知识点。请检查识别文本，或从候选知识点中选择后再解题。"
        result["answer"] = result["coverage_note"]
        result["final_answer"] = ""
        result["steps"] = []
        result["exercises"] = []
        result["learning_path"] = result.get("learning_path") or {"prerequisites": [], "body": "", "consolidation": [], "exercises": []}
        result.pop("prompt", None)
        return result
    try:
        prompt = f"""你是中小学数学解题助教。请解答下面的题目，但不要编造教材出处；教材出处和知识点只以给定图谱证据为准。
题目：{text}
知识点：{result.get('knowledge_point')}
图谱前置知识：{result.get('prerequisite_gaps')}
教材出处：{result.get('source')}

只返回合法 JSON，不要 Markdown 代码块，格式必须是：
{{"steps":[{{"title":"步骤标题","content":"步骤说明"}}],"final_answer":"最终答案","exercises":[{{"question":"巩固题1"}},{{"question":"巩固题2"}}]}}
必须有至少 2 道巩固题；步骤要说明计算依据，最终答案要明确。"""
        raw = _generator.generate(prompt)
        result["answer"], result["exercises"], result["final_answer"], result["raw_solution"], result["solution_steps"] = _parse_attachment_answer(raw, result.get("knowledge_point") or "该知识点")
        result["steps"] = result["answer"]
        if result.get("learning_path") is not None:
            result["learning_path"]["steps"] = result["solution_steps"]
            result["learning_path"]["final_answer"] = result.get("final_answer", "")
            result["learning_path"]["exercises"] = result["exercises"]
    except Exception:
        logger.exception("attachment answer generation failed type=upstream")
        raise ApiError(502, "UPSTREAM_ERROR", "题目解答生成失败，请稍后重试") from None
    result.pop("prompt", None)
    return result


def _process_pdf_job(attachment_id: str, user_id: str, data: bytes) -> None:
    conn = connect()
    try:
        attachment_service.mark_ocr(conn, user_id, attachment_id, "processing")
        result = pdf_service.process_pdf(data)
        attachment_service.mark_pdf_result(conn, user_id, attachment_id, result)
    except ApiError as exc:
        conn.execute("UPDATE attachments SET ocr_status = 'failed', error_code = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                     (exc.code, now_utc(), attachment_id, user_id))
        conn.commit()
    except Exception:
        logger.exception("pdf processing failed type=internal")
        conn.execute("UPDATE attachments SET ocr_status = 'failed', error_code = 'PDF_PROCESSING_FAILED', updated_at = ? WHERE id = ? AND user_id = ?",
                     (now_utc(), attachment_id, user_id))
        conn.commit()
    finally:
        conn.close()
        with _pdf_jobs_lock:
            _pdf_jobs.discard(attachment_id)


def _submit_pdf(attachment_id: str, user_id: str, data: bytes) -> None:
    with _pdf_jobs_lock:
        if attachment_id in _pdf_jobs or len(_pdf_jobs) >= pdf_service.MAX_ACTIVE_DOCUMENTS:
            raise ApiError(429, "PDF_BUSY", "PDF 处理人数已满，请稍后重试")
        _pdf_jobs.add(attachment_id)
    try:
        _pdf_executor.submit(_process_pdf_job, attachment_id, user_id, data)
    except Exception:
        with _pdf_jobs_lock:
            _pdf_jobs.discard(attachment_id)
        raise


@router.post("")
def upload_attachment(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    conversation_id = _conversation(conn, ctx.user["id"], conversation_id)
    if conversation_id is None:
        conversation = chat_service.create_conversation(
            conn,
            ctx.user["id"],
            title="图片题目",
            grade_at_creation=ctx.user.get("grade"),
        )
        conversation_id = conversation["id"]
    name = (file.filename or "").strip()
    is_pdf = name.lower().endswith(".pdf") or file.content_type == "application/pdf"
    if is_pdf:
        data = file.file.read(pdf_service.MAX_PDF_BYTES + 1)
        doc, _ = pdf_service.validate_pdf(data)
        doc.close()
        row = attachment_service.create_validated(conn, ctx.user["id"], data, name or "document.pdf", conversation_id,
                                                   "application/pdf", 1, 1)
    else:
        data = file.file.read(attachment_service.MAX_IMAGE_BYTES + 1)
        row = attachment_service.create(conn, ctx.user["id"], data, name or "image", conversation_id)
    user_message = chat_service.insert_user_message(conn, ctx.user["id"], conversation_id, "PDF题目" if is_pdf else "图片题目", None)
    row = attachment_service.link_user_message(conn, ctx.user["id"], row["id"], user_message["id"])
    payload = attachment_service.to_public(row)
    payload["conversation_id"] = conversation_id
    if is_pdf:
        try:
            _submit_pdf(row["id"], ctx.user["id"], data)
        except ApiError:
            attachment_service.remove(conn, ctx.user["id"], row["id"])
            raise
        payload["ocr_status"] = "processing"
    return payload


@router.get("")
def list_attachments(ctx: AuthContext = Depends(get_auth_context), conn=Depends(get_db)):
    rows = conn.execute(
        "SELECT * FROM attachments WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 100",
        (ctx.user["id"],),
    ).fetchall()
    return {"items": [attachment_service.to_public(row) for row in rows]}


@router.get("/{attachment_id}")
def get_attachment(attachment_id: str, ctx: AuthContext = Depends(get_auth_context), conn=Depends(get_db)):
    return attachment_service.to_public(attachment_service.get_owned(conn, ctx.user["id"], attachment_id))


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: str, ctx: AuthContext = Depends(get_auth_context), conn=Depends(get_db)):
    attachment_service.remove(conn, ctx.user["id"], attachment_id)
    return {"deleted": True}


@router.get("/{attachment_id}/status")
def attachment_status(attachment_id: str, ctx: AuthContext = Depends(get_auth_context), conn=Depends(get_db)):
    return attachment_service.to_public(attachment_service.get_owned(conn, ctx.user["id"], attachment_id))


@router.post("/{attachment_id}/recognize")
def recognize_attachment(attachment_id: str, ctx: AuthContext = Depends(get_auth_context), conn=Depends(get_db)):
    row = attachment_service.get_owned(conn, ctx.user["id"], attachment_id)
    if row["media_type"] == "application/pdf":
        _submit_pdf(row["id"], ctx.user["id"], attachment_service.read_bytes(row))
        attachment_service.mark_ocr(conn, ctx.user["id"], attachment_id, "processing")
        return attachment_service.to_public(attachment_service.get_owned(conn, ctx.user["id"], attachment_id))
    started = time.monotonic()
    attachment_service.mark_ocr(conn, ctx.user["id"], attachment_id, "processing")
    try:
        result = get_ocr_adapter().recognize(attachment_service.read_bytes(row), row["media_type"])
        text = (result.text or "").strip()
        if not text:
            raise ApiError(422, "OCR_EMPTY", "未识别到题目文字，请编辑文本后继续")
        row = attachment_service.mark_ocr(conn, ctx.user["id"], attachment_id, "completed", text, result.confidence)
        return attachment_service.to_public(row)
    except ApiError:
        attachment_service.mark_ocr(conn, ctx.user["id"], attachment_id, "failed")
        raise
    except TimeoutError:
        attachment_service.mark_ocr(conn, ctx.user["id"], attachment_id, "failed")
        raise ApiError(504, "OCR_TIMEOUT", "图片识别超时，请稍后重试") from None
    except Exception:
        logger.exception("ocr failed type=upstream elapsed_ms=%d", int((time.monotonic() - started) * 1000))
        attachment_service.mark_ocr(conn, ctx.user["id"], attachment_id, "failed")
        raise ApiError(502, "OCR_UPSTREAM_ERROR", "图片识别服务暂时不可用") from None


@router.post("/{attachment_id}/solve")
def solve_attachment(attachment_id: str, req: AttachmentSolveRequest, ctx: AuthContext = Depends(get_auth_context), conn=Depends(get_db)):
    row = attachment_service.get_owned(conn, ctx.user["id"], attachment_id)
    conversation_id = _conversation(conn, ctx.user["id"], req.conversation_id or row["conversation_id"])
    result = _solve(req.text, req.knowledge_point_id)
    meta = result.pop("_meta", None)
    result.pop("prompt", None)
    user_message = row["user_message_id"]
    if user_message is None:
        user_message = chat_service.insert_user_message(conn, ctx.user["id"], conversation_id, req.text, None)["id"]
        attachment_service.link_user_message(conn, ctx.user["id"], attachment_id, user_message)
    else:
        conn.execute("UPDATE messages SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?", (req.text, __import__('src.security', fromlist=['now_utc']).now_utc(), user_message, ctx.user["id"]))
        conn.commit()
    versions = chat_service.active_graph_version_ids(conn)
    assistant_message = chat_service.insert_assistant_message(
        conn, ctx.user["id"], conversation_id, content=result.get("answer"),
        status="completed", refused=bool(result.get("refused")),
        knowledge_point=result.get("knowledge_point"), source=result.get("source"),
        prerequisite_gaps=result.get("prerequisite_gaps"), learning_path=result.get("learning_path"),
        graph_version_id=versions.get("full_version_id") or versions.get("book_version_id"),
        context_graph_version_id=versions.get("full_version_id"), reply_to_message_id=user_message,
        meta=meta,
    )
    result["assistant_message_id"] = assistant_message["id"]
    result["attachment_id"] = attachment_id
    result["conversation_id"] = conversation_id
    row = attachment_service.save_solution(conn, ctx.user["id"], attachment_id, req.text, result)
    result["attachment"] = attachment_service.to_public(row)
    return result


@router.get("/{attachment_id}/content")
def attachment_content(attachment_id: str, ctx: AuthContext = Depends(get_auth_context), conn=Depends(get_db)):
    row = attachment_service.get_owned(conn, ctx.user["id"], attachment_id)
    data = attachment_service.read_bytes(row)
    return Response(content=data, media_type=row["media_type"], headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
