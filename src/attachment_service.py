"""Private image attachment storage and ownership helpers for the first image-QA MVP."""

from __future__ import annotations

import hashlib
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

# 存储前把长边压到 1600px，JPEG quality 85；足够 OCR，但能显著减少磁盘占用。
MAX_STORED_EDGE = 1600
JPEG_QUALITY = 85
DEFAULT_QUOTA_BYTES = 200 * 1024 * 1024

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


def prepare_image(data: bytes) -> tuple[bytes, str, int, int]:
    """校验并压缩图片；压缩没有收益时保留原图。"""
    media_type, width, height = validate_image(data)
    try:
        from PIL import Image, ImageOps
    except ModuleNotFoundError:
        raise ApiError(503, "IMAGE_DEPENDENCY_MISSING", "图片处理依赖未安装，请联系管理员") from None

    try:
        with Image.open(io.BytesIO(data)) as raw:
            image = ImageOps.exif_transpose(raw)
            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, (255, 255, 255))
                background.paste(rgba, mask=rgba.split()[-1])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            scale = min(1.0, MAX_STORED_EDGE / max(image.width, image.height))
            if scale < 1.0:
                image = image.resize(
                    (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                    Image.LANCZOS,
                )
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            compressed = buffer.getvalue()
            if len(compressed) < len(data):
                return compressed, "image/jpeg", image.width, image.height
    except (OSError, ValueError):
        raise _bad_image() from None
    return data, media_type, width, height


def _quota_bytes() -> int:
    try:
        return int(os.getenv("IKGR_ATTACHMENT_QUOTA_BYTES", str(DEFAULT_QUOTA_BYTES)))
    except (TypeError, ValueError):
        return DEFAULT_QUOTA_BYTES


def _used_bytes(conn, user_id: str) -> int:
    """按物理文件去重后计算用户已用空间。"""
    row = conn.execute(
        "SELECT COALESCE(SUM(size), 0) FROM ("
        "  SELECT MAX(byte_size) AS size FROM attachments "
        "  WHERE user_id = ? AND deleted_at IS NULL GROUP BY storage_name"
        ")",
        (user_id,),
    ).fetchone()
    return int(row[0] or 0)


def _user_has_storage(conn, user_id: str, storage_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM attachments "
        "WHERE user_id = ? AND storage_name = ? AND deleted_at IS NULL LIMIT 1",
        (user_id, storage_name),
    ).fetchone() is not None


def _check_quota(conn, user_id: str, extra_bytes: int) -> None:
    quota = _quota_bytes()
    if quota <= 0:
        return
    if _used_bytes(conn, user_id) + max(0, extra_bytes) > quota:
        raise ApiError(
            413,
            "ATTACHMENT_QUOTA_EXCEEDED",
            "附件空间已满，请先删除旧附件后再试",
        )


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
    prepared, media_type, width, height = prepare_image(data)
    return create_validated(
        conn,
        user_id,
        prepared,
        original_name,
        conversation_id,
        media_type,
        width,
        height,
        original_byte_size=len(data),
    )


def create_validated(conn, user_id: str, data: bytes, original_name: str, conversation_id: str | None,
                     media_type: str, width: int, height: int,
                     original_byte_size: int | None = None):
    """写入附件；相同 sha256 + media_type 的内容全局复用同一个文件。"""
    if not data:
        raise ApiError(400, "ATTACHMENT_EMPTY", "附件内容为空")

    digest = hashlib.sha256(data).hexdigest()
    original_size = original_byte_size if original_byte_size is not None else len(data)

    existing = conn.execute(
        "SELECT storage_name FROM attachments "
        "WHERE sha256 = ? AND media_type = ? AND deleted_at IS NULL "
        "ORDER BY created_at LIMIT 1",
        (digest, media_type),
    ).fetchone()
    storage_name = existing["storage_name"] if existing else f"{digest}.bin"

    # 同一用户已经有这个物理文件时不再重复计入配额。
    extra = 0 if _user_has_storage(conn, user_id, storage_name) else len(data)
    _check_quota(conn, user_id, extra)

    path = storage_root() / storage_name
    created_file = False
    if not path.exists():
        # 先写临时文件再原子替换，避免并发上传写出半个文件。
        temp_path = path.with_name(f".{storage_name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_bytes(data)
        try:
            os.replace(temp_path, path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        created_file = True

    attachment_id = uuid.uuid4().hex
    now = now_utc()
    try:
        conn.execute(
            """INSERT INTO attachments
            (id, user_id, conversation_id, original_name, media_type, byte_size, width, height,
             storage_name, sha256, original_byte_size, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attachment_id,
                user_id,
                conversation_id,
                (original_name or "image").strip()[:255],
                media_type,
                len(data),
                width,
                height,
                storage_name,
                digest,
                original_size,
                now,
                now,
            ),
        )
        conn.commit()
    except Exception:
        # 只清理本次新建、且没有任何行引用的文件；共享文件不能误删。
        if created_file:
            referenced = conn.execute(
                "SELECT 1 FROM attachments WHERE storage_name = ? LIMIT 1",
                (storage_name,),
            ).fetchone()
            if referenced is None:
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
    # 同一个文件可能被多条记录/多个用户共享，只有最后一条活动记录删除时才删文件。
    remaining = conn.execute(
        "SELECT 1 FROM attachments WHERE storage_name = ? AND deleted_at IS NULL LIMIT 1",
        (row["storage_name"],),
    ).fetchone()
    if remaining is None:
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
