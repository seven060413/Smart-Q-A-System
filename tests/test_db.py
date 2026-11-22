"""阶段 2：数据库迁移（schema_migrations / 建表）测试。"""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from src import db as db_module
from src.schema import MIGRATIONS, apply_migrations, applied_versions

EXPECTED_TABLES = {
    "users",
    "auth_sessions",
    "courses",
    "graph_versions",
    "graph_nodes",
    "graph_edges",
    "graph_edge_targets",
    "conversations",
    "messages",
    "message_knowledge_points",
    "videos",
    "knowledge_point_videos",
    "video_candidates",
    "schema_migrations",
}


@pytest.fixture
def conn():
    c = db_module.connect(":memory:")
    yield c
    c.close()


def _table_names(c: sqlite3.Connection) -> set[str]:
    rows = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r["name"] for r in rows}


def test_migrations_create_all_tables(conn):
    applied = apply_migrations(conn, MIGRATIONS)
    assert [m.version for m in applied] == [m.version for m in MIGRATIONS]
    assert EXPECTED_TABLES <= _table_names(conn)


def test_migrations_are_idempotent(conn):
    apply_migrations(conn, MIGRATIONS)
    second = apply_migrations(conn, MIGRATIONS)
    assert second == []
    assert applied_versions(conn) == {m.version for m in MIGRATIONS}


def test_connection_can_be_used_across_threads():
    """FastAPI 线程池可能在线程 A 建连接、线程 B 使用，不能抛同线程错误。"""
    c = db_module.connect(":memory:")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            value = pool.submit(
                lambda: c.execute("SELECT 1").fetchone()[0]
            ).result()
        assert value == 1
    finally:
        c.close()


def test_foreign_keys_enforced(conn):
    apply_migrations(conn, MIGRATIONS)
    # 插入一条引用不存在用户的会话应被外键拒绝。
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO conversations (id, user_id, course_id, title, created_at, updated_at, last_message_at) "
            "VALUES ('c1', 'missing-user', 'math', 't', '2026-01-01T00:00:00.000Z', "
            "'2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z')"
        )
