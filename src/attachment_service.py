"""Private image attachment storage and ownership helpers for the first image-QA MVP."""

from __future__ import annotations

import io
import json
import os
import uuid
from pathlib import Path

from .errors import ApiError
from .security import now_utc

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_WIDTH = 8192
MAX_IMAGE_HEIGHT = 8192
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_TYPES = {"image/jpeg", "image/png"}

ROOT = Path(__file__).resolve().parents[1]
_STORAGE_ROOT = Path(os.getenv("IKGR_ATTACHMENT_DIR", str(ROOT / "data" / "app" / "attachments")))


def storage_root() -> Path:
    _STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    return _STORAGE_ROOT


def _bad_image(message: str = "图片格式或内容无效") -> ApiError:
    return ApiError(400, "INVALID_IMAGE", message)


def validate_image(data: bytes) -> tuple[str, int, int]:
    try:
        from PIL import Image, UnidentifiedImageError
    except ModuleNotFoundError:
        raise ApiError(503, "IMAGE_DEPENDENCY_MISSING", "图片处理依赖未安装，请联系管理员") from None
    if not data:
        raise _bad_image("图片不能为空")
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError(413, "IMAGE_TOO_LARGE", "图片不能超过 10 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            detected = image.format
            width, height = image.size
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise _bad_image() from None
    if detected == "JPEG":
        media_type = "image/jpeg"
    elif detected == "PNG":
        media_type = "image/png"
    else:
        raise _bad_image("仅支持 JPG 或 PNG 图片")
    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT or width * height > MAX_IMAGE_PIXELS:
        raise ApiError(413, "IMAGE_DIMENSIONS_TOO_LARGE", "图片尺寸或像素总量超过限制")
    return media_type, width, height


def _owned(conn, user_id: str, attachment_id: str):
    row = conn.execute(
        "SELECT * FROM attachments WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (attachment_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "ATTACHMENT_NOT_FOUND", "附件不存在")
    return row


def to_public(row) -> dict:
    return {
        "id": row["id"],
        "conversation_id": row["conversation_id"],
        "original_name": row["original_name"],
        "media_type": row["media_type"],
        "byte_size": row["byte_size"],
        "width": row["width"],
        "height": row["height"],
        "page_count": row["page_count"] if "page_count" in row.keys() else None,
        "page_results": json.loads(row["page_results_json"]) if "page_results_json" in row.keys() and row["page_results_json"] else [],
        "failed_pages": json.loads(row["failed_pages_json"]) if "failed_pages_json" in row.keys() and row["failed_pages_json"] else [],
        "error_code": row["error_code"] if "error_code" in row.keys() else None,
        "ocr_status": row["ocr_status"],
        "ocr_text": row["ocr_text"],
        "ocr_confidence": row["ocr_confidence"],
        "question_text": row["question_text"],
        "solution": json.loads(row["solution_json"]) if row["solution_json"] else None,
        "user_message_id": row["user_message_id"] if "user_message_id" in row.keys() else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create(conn, user_id: str, data: bytes, original_name: str, conversation_id: str | None):
    media_type, width, height = validate_image(data)
    return create_validated(conn, user_id, data, original_name, conversation_id, media_type, width, height)


def create_validated(conn, user_id: str, data: bytes, original_name: str, conversation_id: str | None,
                     media_type: str, width: int, height: int):
    attachment_id = uuid.uuid4().hex
    storage_name = f"{attachment_id}.bin"
    path = storage_root() / storage_name
    path.write_bytes(data)
    now = now_utc()
    try:
        conn.execute(
            """INSERT INTO attachments
            (id, user_id, conversation_id, original_name, media_type, byte_size, width, height,
             storage_name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (attachment_id, user_id, conversation_id, (original_name or "image").strip()[:255],
             media_type, len(data), width, height, storage_name, now, now),
        )
        conn.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()


def get_owned(conn, user_id: str, attachment_id: str):
    return _owned(conn, user_id, attachment_id)


def mark_pdf_result(conn, user_id: str, attachment_id: str, result: dict) -> None:
    _owned(conn, user_id, attachment_id)
    conn.execute(
        """UPDATE attachments SET ocr_status = ?, ocr_text = ?, page_count = ?,
        page_results_json = ?, failed_pages_json = ?, error_code = ?, updated_at = ?
        WHERE id = ? AND user_id = ?""",
        (result["status"], result["text"], result["page_count"],
         json.dumps(result["page_results"], ensure_ascii=False),
         json.dumps(result["failed_pages"]), result.get("error_code"), now_utc(), attachment_id, user_id),
    )
    conn.commit()


def mark_ocr(conn, user_id: str, attachment_id: str, status: str, text: str | None = None, confidence: float | None = None):
    _owned(conn, user_id, attachment_id)
    conn.execute(
        "UPDATE attachments SET ocr_status = ?, ocr_text = ?, ocr_confidence = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (status, text, confidence, now_utc(), attachment_id, user_id),
    )
    conn.commit()
    return _owned(conn, user_id, attachment_id)


def remove(conn, user_id: str, attachment_id: str) -> None:
    row = _owned(conn, user_id, attachment_id)
    conn.execute("UPDATE attachments SET deleted_at = ?, updated_at = ? WHERE id = ? AND user_id = ?", (now_utc(), now_utc(), attachment_id, user_id))
    conn.commit()
    (storage_root() / row["storage_name"]).unlink(missing_ok=True)


def link_user_message(conn, user_id: str, attachment_id: str, message_id: str):
    _owned(conn, user_id, attachment_id)
    conn.execute("UPDATE attachments SET user_message_id = ?, updated_at = ? WHERE id = ? AND user_id = ?", (message_id, now_utc(), attachment_id, user_id))
    conn.commit()
    return _owned(conn, user_id, attachment_id)


def save_solution(conn, user_id: str, attachment_id: str, question_text: str, solution: dict):
    _owned(conn, user_id, attachment_id)
    conn.execute(
        "UPDATE attachments SET question_text = ?, solution_json = ?, solved_at = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (question_text, json.dumps(solution, ensure_ascii=False), now_utc(), now_utc(), attachment_id, user_id),
    )
    conn.commit()
    return _owned(conn, user_id, attachment_id)


def read_bytes(row) -> bytes:
    path = storage_root() / row["storage_name"]
    try:
        return path.read_bytes()
    except OSError:
        raise ApiError(404, "ATTACHMENT_NOT_FOUND", "附件不存在") from None
