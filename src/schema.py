"""数据库 schema 与版本化迁移。

迁移约定：
- MIGRATIONS 按 version 升序排列，每个迁移的 sql 用 executescript 执行；
- 已应用的 version 记录在 schema_migrations 表（由 apply_migrations 自行 bootstrap）；
- 迁移只增不改：新需求追加新 version，不修改已发布的迁移内容；
- 执行入口在 scripts/migrate.py，测试用 tmp 库覆盖同一套逻辑。

表结构设计依据 docs/学生端数据与接口设计.md 第 5 节；本文件是它的可执行实现。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


# version 1：初始 schema（11 张业务表）。
# 说明：
# - 用户/会话/消息用 TEXT UUID，图谱节点/边用 INTEGER 主键；
# - graph_edge_targets 统一承载标量 target 与 target_name_to_ids 列表，避免漏特殊边；
# - messages 用 (conversation_id, user_id) 复合外键防止跨用户写入；
# - 时间一律存 UTC ISO 8601 文本（由 Python 生成，不依赖 SQLite 时间函数）。
INITIAL_SCHEMA = """
CREATE TABLE users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL COLLATE NOCASE,
    display_name    TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'student'
                    CHECK (role IN ('student', 'teacher', 'admin')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'disabled', 'deleted')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    last_login_at   TEXT,
    CONSTRAINT uq_users_username UNIQUE (username)
);

CREATE TABLE auth_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    revoked_at      TEXT,
    last_used_at    TEXT,
    user_agent      TEXT,
    ip_hash         TEXT,
    CONSTRAINT uq_auth_sessions_token_hash UNIQUE (token_hash)
);
CREATE INDEX ix_auth_sessions_user   ON auth_sessions(user_id, expires_at);
CREATE INDEX ix_auth_sessions_expiry ON auth_sessions(expires_at);

CREATE TABLE courses (
    id          TEXT PRIMARY KEY,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL,
    subject     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    CONSTRAINT uq_courses_code UNIQUE (code)
);

CREATE TABLE graph_versions (
    id              TEXT PRIMARY KEY,
    course_id       TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    scope           TEXT NOT NULL
                    CHECK (scope IN ('subject_full', 'book', 'custom')),
    book_id         TEXT,
    active_slot     TEXT NOT NULL,
    dataset_name    TEXT NOT NULL,
    dataset_version TEXT,
    source_path     TEXT NOT NULL,
    source_sha256   TEXT NOT NULL,
    imported_at     TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 0
                    CHECK (is_active IN (0, 1)),
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    CHECK (scope <> 'book' OR book_id IS NOT NULL)
);
CREATE UNIQUE INDEX ux_graph_versions_active_slot
    ON graph_versions(course_id, active_slot)
    WHERE is_active = 1;

CREATE TABLE graph_nodes (
    id                 INTEGER PRIMARY KEY,
    graph_version_id   TEXT NOT NULL REFERENCES graph_versions(id)
                       ON DELETE RESTRICT,
    node_key           TEXT NOT NULL,
    label              TEXT NOT NULL,
    name               TEXT NOT NULL,
    properties_json    TEXT NOT NULL DEFAULT '{}',
    CONSTRAINT uq_graph_nodes_key UNIQUE (graph_version_id, node_key)
);
CREATE INDEX ix_graph_nodes_label ON graph_nodes(graph_version_id, label);
CREATE INDEX ix_graph_nodes_name  ON graph_nodes(graph_version_id, name);

CREATE TABLE graph_edges (
    id                 INTEGER PRIMARY KEY,
    graph_version_id   TEXT NOT NULL REFERENCES graph_versions(id)
                       ON DELETE RESTRICT,
    source_key         TEXT NOT NULL,
    source_name        TEXT,
    type               TEXT NOT NULL,
    source_edge_index  INTEGER NOT NULL,
    properties_json    TEXT NOT NULL DEFAULT '{}',
    CONSTRAINT uq_graph_edges_source_index
        UNIQUE (graph_version_id, source_edge_index),
    CONSTRAINT fk_graph_edges_source
        FOREIGN KEY (graph_version_id, source_key)
        REFERENCES graph_nodes(graph_version_id, node_key)
        ON DELETE RESTRICT
);
CREATE INDEX ix_graph_edges_source ON graph_edges(graph_version_id, source_key, type);
CREATE INDEX ix_graph_edges_type   ON graph_edges(graph_version_id, type);

CREATE TABLE graph_edge_targets (
    edge_id            INTEGER NOT NULL REFERENCES graph_edges(id) ON DELETE CASCADE,
    graph_version_id   TEXT NOT NULL REFERENCES graph_versions(id) ON DELETE RESTRICT,
    ordinal            INTEGER NOT NULL,
    target_key         TEXT NOT NULL,
    target_name        TEXT,
    PRIMARY KEY (edge_id, ordinal),
    CONSTRAINT uq_graph_edge_targets UNIQUE (edge_id, target_key),
    CONSTRAINT fk_graph_edge_targets_target
        FOREIGN KEY (graph_version_id, target_key)
        REFERENCES graph_nodes(graph_version_id, node_key)
        ON DELETE RESTRICT
);
CREATE INDEX ix_graph_edge_targets_target
    ON graph_edge_targets(graph_version_id, target_key);

CREATE TABLE conversations (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    course_id        TEXT NOT NULL REFERENCES courses(id) ON DELETE RESTRICT,
    title            TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    last_message_at  TEXT NOT NULL,
    deleted_at       TEXT,
    CONSTRAINT uq_conversations_id_user UNIQUE (id, user_id)
);
CREATE INDEX ix_conversations_user_list
    ON conversations(user_id, deleted_at, last_message_at DESC, id DESC);

CREATE TABLE messages (
    id                        TEXT PRIMARY KEY,
    conversation_id           TEXT NOT NULL,
    user_id                   TEXT NOT NULL,
    role                      TEXT NOT NULL
                              CHECK (role IN ('user', 'assistant', 'system')),
    content                   TEXT,
    status                    TEXT NOT NULL
                              CHECK (status IN ('completed', 'failed', 'pending')),
    refused                   INTEGER NOT NULL DEFAULT 0
                              CHECK (refused IN (0, 1)),
    knowledge_point           TEXT,
    source                    TEXT,
    learning_path_json        TEXT,
    prerequisite_gaps_json    TEXT,
    graph_version_id          TEXT REFERENCES graph_versions(id) ON DELETE RESTRICT,
    context_graph_version_id  TEXT REFERENCES graph_versions(id) ON DELETE RESTRICT,
    reply_to_message_id       TEXT REFERENCES messages(id) ON DELETE SET NULL,
    client_request_id         TEXT,
    error_code                TEXT,
    error_message             TEXT,
    latency_ms                INTEGER,
    created_at                TEXT NOT NULL,
    updated_at                TEXT NOT NULL,
    CONSTRAINT fk_messages_conversation_user
        FOREIGN KEY (conversation_id, user_id)
        REFERENCES conversations(id, user_id)
        ON DELETE CASCADE
);
CREATE INDEX ix_messages_conversation
    ON messages(conversation_id, created_at, id);
CREATE UNIQUE INDEX ux_messages_client_request
    ON messages(user_id, client_request_id)
    WHERE client_request_id IS NOT NULL;

CREATE TABLE message_knowledge_points (
    message_id        TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    graph_version_id  TEXT NOT NULL REFERENCES graph_versions(id) ON DELETE RESTRICT,
    node_key          TEXT NOT NULL,
    node_name         TEXT,
    relation          TEXT NOT NULL
                      CHECK (relation IN (
                          'body',
                          'prerequisite_required',
                          'prerequisite_suggested',
                          'consolidation'
                      )),
    ordinal           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (message_id, relation, node_key, ordinal)
);
CREATE INDEX ix_mkp_node
    ON message_knowledge_points(graph_version_id, node_key);
"""

MIGRATIONS: list[Migration] = [
    Migration(version=1, name="initial_schema", sql=INITIAL_SCHEMA),
]


def bootstrap_migrations_table(conn) -> None:
    """确保 schema_migrations 表存在（机制本身，不属于版本化迁移）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TEXT NOT NULL
        )
        """
    )


def applied_versions(conn) -> set[int]:
    """返回已应用的迁移版本号集合。"""
    bootstrap_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {r["version"] for r in rows}


def apply_migrations(conn, migrations: list[Migration] | None = None) -> list[Migration]:
    """按版本升序应用未执行的迁移，返回本次实际应用的迁移列表。

    每个迁移单独提交；失败时抛出异常（调用方应使用事务前的文件快照恢复）。
    重复执行是安全的：已应用的版本会被跳过。
    """
    migrations = migrations if migrations is not None else MIGRATIONS
    bootstrap_migrations_table(conn)
    done = applied_versions(conn)
    applied_this_run: list[Migration] = []

    for m in sorted(migrations, key=lambda x: x.version):
        if m.version in done:
            continue
        if any(p.version == m.version and p.name != m.name for p in migrations):
            raise RuntimeError(f"迁移版本 {m.version} 存在冲突定义")
        # executescript 会先提交当前事务，再执行整段 SQL；执行成功后补记版本。
        conn.executescript(m.sql)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) "
            "VALUES (?, ?, ?)",
            (m.version, m.name, _utcnow()),
        )
        conn.commit()
        applied_this_run.append(m)
    return applied_this_run


def _utcnow() -> str:
    """当前 UTC 时间，格式与 API 一致。"""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
