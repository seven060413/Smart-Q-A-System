"""聊天会话与消息的数据库服务（阶段 5）。

所有查询都要求调用方传入已验证的 user_id；这里不读取请求体里的 user_id。
会话归属、软删除、游标分页和失败消息记录都在这一层完成。
"""

from __future__ import annotations

import base64
import json
import uuid

from .errors import ApiError
from .security import now_utc

DEFAULT_COURSE_ID = "math"
DEFAULT_COURSE_NAME = "小学数学"
DEFAULT_TITLE = "新对话"
TITLE_MAX_LEN = 80
AUTO_TITLE_MAX_LEN = 30


def _loads(text, default):
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def title_from_question(question: str) -> str:
    """用第一个问题生成简短标题（不保存完整长问题）。"""
    text = " ".join((question or "").split())
    if not text:
        return DEFAULT_TITLE
    if len(text) > AUTO_TITLE_MAX_LEN:
        return text[:AUTO_TITLE_MAX_LEN] + "…"
    return text


def normalize_title(title: str | None) -> str:
    text = " ".join((title or "").split())
    if not text:
        return DEFAULT_TITLE
    return text[:TITLE_MAX_LEN]


def ensure_course(
    conn,
    course_id: str = DEFAULT_COURSE_ID,
    name: str = DEFAULT_COURSE_NAME,
    subject: str = "math",
) -> None:
    """确保课程存在；已存在时不动。"""
    now = now_utc()
    conn.execute(
        "INSERT OR IGNORE INTO courses "
        "(id, code, name, subject, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (course_id, course_id, name, subject, now, now),
    )


def active_graph_version_ids(conn, course_id: str = DEFAULT_COURSE_ID) -> dict:
    """返回当前启用的 book / subject_full 版本 id（没有则为 None）。"""
    rows = conn.execute(
        "SELECT id, active_slot FROM graph_versions "
        "WHERE course_id = ? AND is_active = 1",
        (course_id,),
    ).fetchall()
    book = next(
        (r["id"] for r in rows if r["active_slot"] == "book:math_5b_rjb"),
        None,
    )
    if book is None:
        book = next(
            (r["id"] for r in rows if r["active_slot"].startswith("book:")),
            None,
        )
    full = next((r["id"] for r in rows if r["active_slot"] == "subject_full"), None)
    return {"book_version_id": book, "full_version_id": full}


def conversation_to_dict(row) -> dict:
    keys = row.keys() if hasattr(row, "keys") else []
    return {
        "id": row["id"],
        "title": row["title"],
        "course_id": row["course_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_message_at": row["last_message_at"],
        "deleted_at": row["deleted_at"],
        "message_count": row["message_count"] if "message_count" in keys else None,
    }


def message_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
        "status": row["status"],
        "refused": bool(row["refused"]),
        "knowledge_point": row["knowledge_point"],
        "source": row["source"],
        "prerequisite_gaps": _loads(row["prerequisite_gaps_json"], []),
        "learning_path": _loads(row["learning_path_json"], None),
        "reply_to_message_id": row["reply_to_message_id"],
        "error_code": row["error_code"],
        "error_message": row["error_message"],
        "graph_version_id": row["graph_version_id"],
        "context_graph_version_id": row["context_graph_version_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def encode_cursor(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(data, dict):
            raise ValueError("cursor must be an object")
        return data
    except Exception:
        raise ApiError(400, "INVALID_CURSOR", "分页游标无效") from None


def create_conversation(
    conn,
    user_id: str,
    title: str | None = None,
    course_id: str = DEFAULT_COURSE_ID,
) -> dict:
    """创建空会话；归属由服务端参数决定。

    默认数学课程会自动确保存在；其他课程必须已经在 courses 表中，
    避免学生通过 API 随意创建课程记录。
    """
    now = now_utc()
    conversation_id = uuid.uuid4().hex
    final_title = normalize_title(title)
    with conn:
        if course_id == DEFAULT_COURSE_ID:
            ensure_course(conn, course_id)
        else:
            exists = conn.execute(
                "SELECT 1 FROM courses WHERE id = ? AND status = 'active'",
                (course_id,),
            ).fetchone()
            if exists is None:
                raise ApiError(400, "COURSE_NOT_FOUND", "课程不存在")
        conn.execute(
            "INSERT INTO conversations "
            "(id, user_id, course_id, title, created_at, updated_at, last_message_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                user_id,
                course_id,
                final_title,
                now,
                now,
                now,
            ),
        )
    return get_conversation(conn, user_id, conversation_id)


def get_conversation(
    conn,
    user_id: str,
    conversation_id: str,
    include_deleted: bool = False,
) -> dict | None:
    sql = (
        "SELECT c.id, c.title, c.course_id, c.created_at, c.updated_at, "
        "       c.last_message_at, c.deleted_at, "
        "       (SELECT COUNT(*) FROM messages m "
        "        WHERE m.conversation_id = c.id) AS message_count "
        "FROM conversations c "
        "WHERE c.id = ? AND c.user_id = ?"
    )
    params = [conversation_id, user_id]
    if not include_deleted:
        sql += " AND c.deleted_at IS NULL"
    row = conn.execute(sql, params).fetchone()
    return conversation_to_dict(row) if row else None


def list_conversations(
    conn,
    user_id: str,
    limit: int = 20,
    cursor: str | None = None,
) -> dict:
    payload = decode_cursor(cursor)
    if payload and (
        payload.get("last_message_at") is None or payload.get("seq") is None
    ):
        raise ApiError(400, "INVALID_CURSOR", "分页游标无效")
    sql = (
        "SELECT c.rowid AS seq, c.id, c.title, c.course_id, c.created_at, "
        "       c.updated_at, c.last_message_at, c.deleted_at, "
        "       (SELECT COUNT(*) FROM messages m "
        "        WHERE m.conversation_id = c.id) AS message_count "
        "FROM conversations c "
        "WHERE c.user_id = ? AND c.deleted_at IS NULL"
    )
    params: list = [user_id]
    if payload:
        sql += (
            " AND (c.last_message_at < ? "
            "      OR (c.last_message_at = ? AND c.rowid < ?))"
        )
        params.extend(
            [
                payload.get("last_message_at"),
                payload.get("last_message_at"),
                payload.get("seq"),
            ]
        )
    sql += " ORDER BY c.last_message_at DESC, c.rowid DESC LIMIT ?"
    params.append(limit + 1)

    rows = conn.execute(sql, params).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [conversation_to_dict(r) for r in rows]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(
            {"last_message_at": last["last_message_at"], "seq": last["seq"]}
        )
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


def list_messages(
    conn,
    conversation_id: str,
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    payload = decode_cursor(cursor)
    if payload and (
        payload.get("created_at") is None or payload.get("seq") is None
    ):
        raise ApiError(400, "INVALID_CURSOR", "分页游标无效")
    sql = (
        "SELECT rowid AS seq, id, role, content, status, refused, "
        "       knowledge_point, source, learning_path_json, "
        "       prerequisite_gaps_json, reply_to_message_id, error_code, "
        "       error_message, graph_version_id, context_graph_version_id, "
        "       created_at, updated_at "
        "FROM messages WHERE conversation_id = ?"
    )
    params: list = [conversation_id]
    if payload:
        sql += " AND (created_at < ? OR (created_at = ? AND rowid < ?))"
        params.extend(
            [
                payload.get("created_at"),
                payload.get("created_at"),
                payload.get("seq"),
            ]
        )
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    params.append(limit + 1)

    rows = conn.execute(sql, params).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode_cursor(
            {"created_at": last["created_at"], "seq": last["seq"]}
        )
    items = [message_to_dict(r) for r in reversed(rows)]
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


def soft_delete_conversation(conn, user_id: str, conversation_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, deleted_at FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()
    if row is None:
        return None
    if row["deleted_at"] is None:
        now = now_utc()
        with conn:
            conn.execute(
                "UPDATE conversations SET deleted_at = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (now, now, conversation_id, user_id),
            )
    return get_conversation(conn, user_id, conversation_id, include_deleted=True)


def find_turn_by_client_request(conn, user_id: str, client_request_id: str):
    """按幂等键查用户消息及其助手回答；返回 (user_row, assistant_row|None)。"""
    user_row = conn.execute(
        "SELECT * FROM messages "
        "WHERE user_id = ? AND client_request_id = ? AND role = 'user' "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id, client_request_id),
    ).fetchone()
    if user_row is None:
        return None, None
    assistant_row = conn.execute(
        "SELECT * FROM messages "
        "WHERE reply_to_message_id = ? AND role = 'assistant' "
        "ORDER BY created_at DESC LIMIT 1",
        (user_row["id"],),
    ).fetchone()
    return user_row, assistant_row


def insert_user_message(
    conn,
    user_id: str,
    conversation_id: str,
    content: str,
    client_request_id: str | None,
) -> dict:
    """写入用户问题，并更新会话时间；首问时自动生成标题。"""
    message_id = uuid.uuid4().hex
    now = now_utc()

    with conn:
        conv = conn.execute(
            "SELECT title FROM conversations "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (conversation_id, user_id),
        ).fetchone()
        if conv is None:
            raise ApiError(404, "CONVERSATION_NOT_FOUND", "会话不存在")

        count = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()["c"]

        conn.execute(
            "INSERT INTO messages "
            "(id, conversation_id, user_id, role, content, status, refused, "
            " client_request_id, created_at, updated_at) "
            "VALUES (?, ?, ?, 'user', ?, 'completed', 0, ?, ?, ?)",
            (
                message_id,
                conversation_id,
                user_id,
                content,
                client_request_id,
                now,
                now,
            ),
        )

        if count == 0 and conv["title"] in (DEFAULT_TITLE, ""):
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
                (title_from_question(content), conversation_id, user_id),
            )
        conn.execute(
            "UPDATE conversations SET last_message_at = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (now, now, conversation_id, user_id),
        )

    return {"id": message_id, "conversation_id": conversation_id, "created_at": now}


def insert_assistant_message(
    conn,
    user_id: str,
    conversation_id: str,
    *,
    content: str | None,
    status: str,
    refused: bool,
    knowledge_point: str | None,
    source: str | None,
    prerequisite_gaps: list | None,
    learning_path: dict | None,
    graph_version_id: str | None,
    context_graph_version_id: str | None,
    reply_to_message_id: str,
    meta: dict | None,
    error_code: str | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> dict:
    """写入助手回答（成功或失败），并保存知识点关联。"""
    message_id = uuid.uuid4().hex
    now = now_utc()

    with conn:
        conn.execute(
            "INSERT INTO messages "
            "(id, conversation_id, user_id, role, content, status, refused, "
            " knowledge_point, source, learning_path_json, prerequisite_gaps_json, "
            " graph_version_id, context_graph_version_id, reply_to_message_id, "
            " error_code, error_message, latency_ms, created_at, updated_at) "
            "VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                message_id,
                conversation_id,
                user_id,
                content,
                status,
                1 if refused else 0,
                knowledge_point,
                source,
                json.dumps(learning_path, ensure_ascii=False),
                json.dumps(prerequisite_gaps or [], ensure_ascii=False),
                graph_version_id,
                context_graph_version_id,
                reply_to_message_id,
                error_code,
                error_message,
                latency_ms,
                now,
                now,
            ),
        )

        _insert_knowledge_points(
            conn,
            message_id,
            meta,
            graph_version_id or context_graph_version_id,
            context_graph_version_id or graph_version_id,
        )

        conn.execute(
            "UPDATE conversations SET last_message_at = ?, updated_at = ? "
            "WHERE id = ? AND user_id = ?",
            (now, now, conversation_id, user_id),
        )

    return {"id": message_id, "created_at": now}


def _insert_knowledge_points(
    conn,
    message_id: str,
    meta: dict | None,
    book_version_id: str | None,
    full_version_id: str | None,
) -> None:
    """把本体/前置/巩固知识点拆到 message_knowledge_points。"""
    if not meta:
        return
    default_version = book_version_id or full_version_id
    if default_version is None:
        # 图谱版本尚未导入时仍保存消息，只是不写知识点关联。
        return

    rows: list[tuple[dict, str, str]] = []
    if meta.get("body"):
        rows.append((meta["body"], "body", book_version_id or default_version))
    for item in meta.get("required", []):
        rows.append((item, "prerequisite_required", full_version_id or default_version))
    for item in meta.get("suggested", []):
        rows.append((item, "prerequisite_suggested", full_version_id or default_version))
    for item in meta.get("consolidation", []):
        rows.append((item, "consolidation", full_version_id or default_version))

    for ordinal, (item, relation, version_id) in enumerate(rows):
        conn.execute(
            "INSERT OR IGNORE INTO message_knowledge_points "
            "(message_id, graph_version_id, node_key, node_name, relation, ordinal) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                message_id,
                version_id,
                item.get("id"),
                item.get("name"),
                relation,
                ordinal,
            ),
        )


def stored_turn_response(user_row, assistant_row) -> dict:
    """把已存在的问答对转成 /api/ask 响应（用于幂等重放）。"""
    if assistant_row is None:
        raise ApiError(
            409,
            "REQUEST_IN_PROGRESS",
            "该请求正在处理中，请稍后再试",
            details={"conversation_id": user_row["conversation_id"]},
        )
    if assistant_row["status"] == "failed":
        raise ApiError(
            502,
            assistant_row["error_code"] or "UPSTREAM_ERROR",
            assistant_row["error_message"] or "回答生成失败，请稍后重试",
            details={
                "conversation_id": user_row["conversation_id"],
                "user_message_id": user_row["id"],
                "assistant_message_id": assistant_row["id"],
            },
        )
    return {
        "answer": assistant_row["content"],
        "knowledge_point": assistant_row["knowledge_point"],
        "prerequisite_gaps": _loads(assistant_row["prerequisite_gaps_json"], []),
        "learning_path": _loads(assistant_row["learning_path_json"], None),
        "source": assistant_row["source"],
        "refused": bool(assistant_row["refused"]),
        "persisted": True,
        "conversation_id": user_row["conversation_id"],
        "user_message_id": user_row["id"],
        "assistant_message_id": assistant_row["id"],
        "created_at": assistant_row["created_at"],
        "deduplicated": True,
    }
