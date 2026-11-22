"""服务端清理脚本：过期会话、旧诊断、软删除会话/附件与孤儿文件。"""

import importlib.util
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import db as db_module
from src.schema import apply_migrations

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_data.py"


def _load_cleanup_module():
    spec = importlib.util.spec_from_file_location("cleanup_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iso(delta_days: float) -> str:
    value = datetime.now(timezone.utc) + timedelta(days=delta_days)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _seed(db_path: Path, attachments: Path) -> None:
    attachments.mkdir(parents=True, exist_ok=True)
    now = _iso(0)
    old = _iso(-400)
    recent = _iso(-10)
    expired = _iso(-1)
    future = _iso(30)

    for name, mtime in (
        ("old-conv.bin", time.time() - 7200),
        ("old-soft.bin", time.time() - 7200),
        ("active.bin", time.time()),
        ("recent-soft.bin", time.time()),
        ("orphan.bin", time.time() - 7200),
    ):
        path = attachments / name
        path.write_bytes(b"x")
        os.utime(path, (mtime, mtime))

    conn = db_module.connect(db_path)
    try:
        apply_migrations(conn)
        with conn:
            conn.execute(
                "INSERT INTO users (id, username, display_name, password_hash, role, status, "
                "created_at, updated_at) VALUES ('u1', 'u1', 'u1', 'x', 'student', 'active', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO courses (id, code, name, subject, status, created_at, updated_at) "
                "VALUES ('math', 'math', '数学', 'math', 'active', ?, ?)",
                (now, now),
            )
            # 过期/有效登录会话
            conn.execute(
                "INSERT INTO auth_sessions (id, user_id, token_hash, created_at, expires_at) "
                "VALUES ('s_expired', 'u1', 'h1', ?, ?)",
                (old, expired),
            )
            conn.execute(
                "INSERT INTO auth_sessions (id, user_id, token_hash, created_at, expires_at) "
                "VALUES ('s_active', 'u1', 'h2', ?, ?)",
                (now, future),
            )

            # 旧完成、最近完成、旧进行中诊断
            for sid, created, status in (
                ("q_old", old, "completed"),
                ("q_recent", recent, "completed"),
                ("q_active", old, "active"),
            ):
                conn.execute(
                    "INSERT INTO quiz_sessions "
                    "(id, user_id, mode, grade, semester, scope_json, max_questions, mastery_streak, "
                    " status, state_json, result_json, created_at, updated_at, finished_at, expires_at) "
                    "VALUES (?, 'u1', 'single', 5, 'all', '{}', 16, 3, ?, '{}', NULL, ?, ?, NULL, ?)",
                    (sid, status, created, created, future),
                )
                conn.execute(
                    "INSERT INTO quiz_attempts "
                    "(session_id, question_id, node_key, ordinal, student_answer, is_correct, created_at) "
                    "VALUES (?, ?, 'cnm_p132', 1, 'x', 0, ?)",
                    (sid, f"q_{sid}", created),
                )

            # 旧软删除、最近软删除、正常会话
            for cid, deleted in (
                ("c_old", old),
                ("c_recent", recent),
                ("c_active", None),
            ):
                conn.execute(
                    "INSERT INTO conversations "
                    "(id, user_id, course_id, title, created_at, updated_at, last_message_at, deleted_at) "
                    "VALUES (?, 'u1', 'math', 't', ?, ?, ?, ?)",
                    (cid, old if deleted else now, old if deleted else now, old if deleted else now, deleted),
                )
                conn.execute(
                    "INSERT INTO messages "
                    "(id, conversation_id, user_id, role, content, status, refused, created_at, updated_at) "
                    "VALUES (?, ?, 'u1', 'user', 'x', 'completed', 0, ?, ?)",
                    (f"m_{cid}", cid, old if deleted else now, old if deleted else now),
                )

            for aid, cid, storage, deleted in (
                ("a_old_conv", "c_old", "old-conv.bin", None),
                ("a_old_soft", "c_recent", "old-soft.bin", old),
                ("a_active", "c_active", "active.bin", None),
                ("a_recent_soft", "c_active", "recent-soft.bin", recent),
            ):
                conn.execute(
                    "INSERT INTO attachments "
                    "(id, user_id, conversation_id, original_name, media_type, byte_size, "
                    " width, height, storage_name, created_at, updated_at, deleted_at) "
                    "VALUES (?, 'u1', ?, 'x.jpg', 'image/jpeg', 1, 1, 1, ?, ?, ?, ?)",
                    (aid, cid, storage, now, now, deleted),
                )
    finally:
        conn.close()


def test_cleanup_dry_run_counts_without_deleting(tmp_path):
    module = _load_cleanup_module()
    db_path = tmp_path / "cleanup.db"
    attachments = tmp_path / "attachments"
    _seed(db_path, attachments)

    stats = module.cleanup(
        db_path=db_path, days=365, dry_run=True, orphans=True, attachments_dir=attachments
    )
    assert stats["auth_sessions"] == 1
    assert stats["quiz_sessions"] == 1
    assert stats["quiz_attempts"] == 1
    assert stats["conversations"] == 1
    assert stats["messages"] == 1
    assert stats["attachments_soft_deleted"] == 1
    assert stats["attachments_in_deleted_conversations"] == 1
    assert stats["orphan_files"] == 1

    conn = db_module.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM quiz_sessions").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 3
        assert conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 4
    finally:
        conn.close()
    assert (attachments / "old-conv.bin").exists()


def test_cleanup_removes_old_rows_and_unreferenced_files(tmp_path):
    module = _load_cleanup_module()
    db_path = tmp_path / "cleanup.db"
    attachments = tmp_path / "attachments"
    _seed(db_path, attachments)

    module.cleanup(
        db_path=db_path, days=365, dry_run=False, orphans=True, attachments_dir=attachments
    )

    conn = db_module.connect(db_path)
    try:
        assert [r[0] for r in conn.execute("SELECT id FROM auth_sessions")] == ["s_active"]
        assert {r[0] for r in conn.execute("SELECT id FROM quiz_sessions")} == {
            "q_recent",
            "q_active",
        }
        assert {r[0] for r in conn.execute("SELECT session_id FROM quiz_attempts")} == {
            "q_recent",
            "q_active",
        }
        assert {r[0] for r in conn.execute("SELECT id FROM conversations")} == {
            "c_recent",
            "c_active",
        }
        assert {r[0] for r in conn.execute("SELECT conversation_id FROM messages")} == {
            "c_recent",
            "c_active",
        }
        assert {r[0] for r in conn.execute("SELECT id FROM attachments")} == {
            "a_active",
            "a_recent_soft",
        }
    finally:
        conn.close()

    assert not (attachments / "old-conv.bin").exists()
    assert not (attachments / "old-soft.bin").exists()
    assert not (attachments / "orphan.bin").exists()
    assert (attachments / "active.bin").exists()
    assert (attachments / "recent-soft.bin").exists()
