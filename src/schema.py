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

# version 2：知识点关联视频。
# 说明：
# - 视频按 node_key（graph_nodes.node_key / run_qa._meta.*.id）关联，不按
#   (graph_version_id, node_key) 关联：本体与前置在 message_knowledge_points 中
#   可能写入不同图谱版本，但 node_key 是同一套稳定 ID；
# - 不建 node_key 到 graph_nodes 的外键：图谱版本 --force 重导会删节点，
#   外键会阻塞重导；source_graph_version_id 只做来源记录；
# - review_status 记在映射上，videos.status 记视频本身（失效/下架）；
# - 只有 approved + active 会在查询接口返回。
KNOWLEDGE_POINT_VIDEOS_SCHEMA = """
CREATE TABLE videos (
    id                  TEXT PRIMARY KEY,
    platform            TEXT NOT NULL DEFAULT 'bilibili'
                        CHECK (platform IN ('bilibili')),
    bvid                TEXT NOT NULL,
    page                INTEGER NOT NULL DEFAULT 1 CHECK (page >= 1),
    aid                 INTEGER,
    title               TEXT NOT NULL,
    author              TEXT,
    duration_seconds    INTEGER,
    cover_url           TEXT,
    watch_url           TEXT NOT NULL,
    published_at        TEXT,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'unavailable', 'hidden')),
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CONSTRAINT uq_videos_bvid_page UNIQUE (platform, bvid, page)
);
CREATE INDEX ix_videos_status ON videos(status);

CREATE TABLE knowledge_point_videos (
    id                  INTEGER PRIMARY KEY,
    course_id           TEXT NOT NULL DEFAULT 'math'
                        REFERENCES courses(id) ON DELETE RESTRICT,
    node_key            TEXT NOT NULL,
    node_name           TEXT,
    video_id            TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    relation            TEXT NOT NULL DEFAULT 'explains'
                        CHECK (relation IN ('explains', 'prerequisite')),
    rank                INTEGER NOT NULL DEFAULT 0,
    review_status       TEXT NOT NULL DEFAULT 'pending'
                        CHECK (review_status IN ('pending', 'approved', 'rejected')),
    review_note         TEXT,
    reviewed_by         TEXT,
    reviewed_at         TEXT,
    source_graph_version_id TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CONSTRAINT uq_kpv UNIQUE (course_id, node_key, video_id, relation),
    CHECK (review_status <> 'approved' OR reviewed_at IS NOT NULL)
);
CREATE INDEX ix_kpv_lookup
    ON knowledge_point_videos(course_id, node_key, review_status, rank);
CREATE INDEX ix_kpv_video
    ON knowledge_point_videos(video_id);

CREATE TABLE video_candidates (
    id                  INTEGER PRIMARY KEY,
    course_id           TEXT NOT NULL DEFAULT 'math',
    node_key            TEXT NOT NULL,
    query               TEXT NOT NULL,
    platform            TEXT NOT NULL DEFAULT 'bilibili',
    bvid                TEXT NOT NULL,
    page                INTEGER NOT NULL DEFAULT 1,
    title               TEXT,
    author              TEXT,
    duration_seconds    INTEGER,
    cover_url           TEXT,
    play_count          INTEGER,
    published_at        TEXT,
    search_rank         INTEGER,
    raw_json            TEXT NOT NULL DEFAULT '{}',
    fetched_at          TEXT NOT NULL,
    CONSTRAINT uq_video_candidates
        UNIQUE (course_id, node_key, query, platform, bvid, page)
);
CREATE INDEX ix_video_candidates_pending
    ON video_candidates(course_id, node_key, fetched_at);
"""

# version 3：B 站官方嵌入播放器需要的 aid / cid。
# - videos.aid 在 version 2 已有，这里补 cid；
# - video_candidates 增加 aid/cid，便于审核时或事后解析；
# - 官方嵌入格式：?isOutside=true&aid=...&bvid=...&cid=...&p=...
VIDEO_EMBED_METADATA_SCHEMA = """
ALTER TABLE videos ADD COLUMN cid INTEGER;
ALTER TABLE video_candidates ADD COLUMN aid INTEGER;
ALTER TABLE video_candidates ADD COLUMN cid INTEGER;
"""

ATTACHMENTS_SCHEMA = """
CREATE TABLE attachments (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    original_name   TEXT NOT NULL,
    media_type      TEXT NOT NULL CHECK (media_type IN ('image/jpeg', 'image/png')),
    byte_size       INTEGER NOT NULL CHECK (byte_size > 0),
    width           INTEGER NOT NULL CHECK (width > 0),
    height          INTEGER NOT NULL CHECK (height > 0),
    storage_name    TEXT NOT NULL UNIQUE,
    ocr_status      TEXT NOT NULL DEFAULT 'pending'
                    CHECK (ocr_status IN ('pending', 'processing', 'completed', 'failed')),
    ocr_text        TEXT,
    ocr_confidence  REAL,
    question_text   TEXT,
    solution_json   TEXT,
    solved_at       TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    deleted_at      TEXT
);
CREATE INDEX ix_attachments_user ON attachments(user_id, created_at);
CREATE INDEX ix_attachments_conversation ON attachments(conversation_id, created_at);
"""

# version 8：学情诊断题库与会话。
# 说明：
# - questions 以 (dataset_version, id) 为主键，允许同一题库有多个版本；
# - quiz_sessions 同时服务登录用户和游客（user_id 为 NULL），state_json 存引擎状态；
# - quiz_attempts 记录每题作答，client_request_id 用于提交重试幂等；
# - 答案只存在服务端，接口永不返回 answer。
QUIZ_SCHEMA = """
CREATE TABLE questions (
    dataset_version TEXT NOT NULL,
    id              TEXT NOT NULL,
    node_key        TEXT NOT NULL,
    node_name       TEXT,
    grade           INTEGER,
    chapter         TEXT,
    difficulty      TEXT NOT NULL,
    type            TEXT NOT NULL,
    prompt          TEXT NOT NULL,
    choices_json    TEXT,
    answer          TEXT NOT NULL,
    explanation     TEXT,
    figure_svg      TEXT,
    verify_expr     TEXT,
    hide_choice_text INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (dataset_version, id)
);
CREATE INDEX ix_questions_node ON questions(dataset_version, node_key);

CREATE TABLE quiz_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT REFERENCES users(id) ON DELETE SET NULL,
    mode            TEXT NOT NULL CHECK (mode IN ('single', 'chapter', 'grade')),
    grade           INTEGER,
    semester        TEXT,
    scope_json      TEXT NOT NULL,
    max_questions   INTEGER NOT NULL CHECK (max_questions > 0),
    mastery_streak  INTEGER NOT NULL CHECK (mastery_streak IN (2, 3, 5)),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'completed', 'aborted')),
    state_json      TEXT NOT NULL,
    result_json     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    finished_at     TEXT,
    expires_at      TEXT NOT NULL
);
CREATE INDEX ix_quiz_sessions_user ON quiz_sessions(user_id, created_at DESC);
CREATE INDEX ix_quiz_sessions_expiry ON quiz_sessions(expires_at);

CREATE TABLE quiz_attempts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    question_id       TEXT NOT NULL,
    node_key          TEXT NOT NULL,
    ordinal           INTEGER NOT NULL,
    student_answer    TEXT,
    is_correct        INTEGER NOT NULL CHECK (is_correct IN (0, 1)),
    client_request_id TEXT,
    response_json     TEXT,
    created_at        TEXT NOT NULL,
    CONSTRAINT uq_quiz_attempt_question UNIQUE (session_id, question_id),
    CONSTRAINT uq_quiz_attempt_ordinal UNIQUE (session_id, ordinal)
);
CREATE INDEX ix_quiz_attempts_session ON quiz_attempts(session_id, ordinal);
CREATE UNIQUE INDEX ux_quiz_attempts_client
    ON quiz_attempts(session_id, client_request_id)
    WHERE client_request_id IS NOT NULL;
"""

# version 10：持续学习闭环。
# 说明：
# - quiz_sessions 记录题库版本与范围总数，供趋势比较与覆盖率计算；
# - quiz_attempts 记录作答时的题目快照，题库更新后错题集内容保持不变；
# - wrong_question_marks 只存用户对错题的标记（待复习/已掌握/已忽略），
#   不修改 attempts；
# - 旧数据新列为 NULL，读接口按 pansgo.SOURCE_COMMIT / 当前题库回退。
LEARNING_LOOP_SCHEMA = """
ALTER TABLE quiz_sessions ADD COLUMN dataset_version TEXT;
ALTER TABLE quiz_sessions ADD COLUMN scope_count INTEGER;

ALTER TABLE quiz_attempts ADD COLUMN dataset_version TEXT;
ALTER TABLE quiz_attempts ADD COLUMN difficulty TEXT;
ALTER TABLE quiz_attempts ADD COLUMN topic_name TEXT;
ALTER TABLE quiz_attempts ADD COLUMN chapter TEXT;
ALTER TABLE quiz_attempts ADD COLUMN grade INTEGER;
ALTER TABLE quiz_attempts ADD COLUMN prompt_snapshot TEXT;
ALTER TABLE quiz_attempts ADD COLUMN choices_snapshot_json TEXT;
ALTER TABLE quiz_attempts ADD COLUMN answer_snapshot TEXT;
ALTER TABLE quiz_attempts ADD COLUMN explanation_snapshot TEXT;
ALTER TABLE quiz_attempts ADD COLUMN figure_snapshot TEXT;

CREATE TABLE wrong_question_marks (
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dataset_version TEXT NOT NULL,
    question_id     TEXT NOT NULL,
    node_key        TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'mastered', 'ignored')),
    updated_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, dataset_version, question_id)
);
CREATE INDEX ix_wrong_marks_user
    ON wrong_question_marks(user_id, status, updated_at DESC);

CREATE INDEX ix_quiz_sessions_user_time
    ON quiz_sessions(user_id, created_at DESC);

CREATE INDEX ix_quiz_attempts_user_wrong
    ON quiz_attempts(session_id, is_correct, created_at);
"""

# version 11：学生年级。
# 说明：
# - users.grade 是「当前年级」，只允许 1-9（小学一年级到初中九年级）；
# - grade_updated_at 记录年级变更时间，供学段升级提示与推荐解释使用；
# - conversations.grade_at_creation 是会话创建时的年级快照，只用于解释历史，
#   不参与聊天过滤（聊天始终按内容跨年级召回）。
STUDENT_GRADE_SCHEMA = """
ALTER TABLE users ADD COLUMN grade INTEGER CHECK (grade BETWEEN 1 AND 9);
ALTER TABLE users ADD COLUMN grade_updated_at TEXT;

ALTER TABLE conversations ADD COLUMN grade_at_creation INTEGER;
"""

# version 12：附件内容去重。
# 说明：
# - storage_name 不再 UNIQUE：同一份内容可以被多条附件记录引用；
# - sha256 记录存储内容的哈希，新上传按哈希全局去重；
# - original_byte_size 记录压缩前大小，便于统计压缩效果；
# - 旧数据 sha256 为 NULL，由后续回填脚本补齐。
ATTACHMENT_DEDUPE_SCHEMA = """
PRAGMA foreign_keys = OFF;
CREATE TABLE attachments_v12 (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    original_name TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('image/jpeg', 'image/png', 'application/pdf')),
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    storage_name TEXT NOT NULL,
    sha256 TEXT,
    original_byte_size INTEGER,
    ocr_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (ocr_status IN ('pending', 'processing', 'completed', 'partial', 'failed')),
    ocr_text TEXT,
    ocr_confidence REAL,
    question_text TEXT,
    solution_json TEXT,
    solved_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    user_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
    page_count INTEGER,
    page_results_json TEXT,
    failed_pages_json TEXT NOT NULL DEFAULT '[]',
    error_code TEXT
);
INSERT INTO attachments_v12
SELECT id, user_id, conversation_id, original_name, media_type, byte_size, width, height,
       storage_name, NULL, NULL, ocr_status, ocr_text, ocr_confidence, question_text,
       solution_json, solved_at, created_at, updated_at, deleted_at, user_message_id,
       page_count, page_results_json, failed_pages_json, error_code
FROM attachments;
DROP TABLE attachments;
ALTER TABLE attachments_v12 RENAME TO attachments;
CREATE INDEX ix_attachments_user ON attachments(user_id, created_at);
CREATE INDEX ix_attachments_conversation ON attachments(conversation_id, created_at);
CREATE INDEX ix_attachments_storage ON attachments(storage_name);
CREATE INDEX ix_attachments_sha ON attachments(sha256, media_type);
PRAGMA foreign_keys = ON;
"""

MIGRATIONS: list[Migration] = [
    Migration(version=1, name="initial_schema", sql=INITIAL_SCHEMA),
    Migration(
        version=2,
        name="knowledge_point_videos",
        sql=KNOWLEDGE_POINT_VIDEOS_SCHEMA,
    ),
    Migration(
        version=3,
        name="video_embed_metadata",
        sql=VIDEO_EMBED_METADATA_SCHEMA,
    ),
    Migration(version=4, name="attachments", sql=ATTACHMENTS_SCHEMA),
    Migration(
        version=5,
        name="attachment_message_link",
        sql="ALTER TABLE attachments ADD COLUMN user_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL;",
    ),
    Migration(
        version=6,
        name="pdf_attachment_processing",
        sql="""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE attachments_v6 (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
            original_name TEXT NOT NULL,
            media_type TEXT NOT NULL CHECK (media_type IN ('image/jpeg', 'image/png', 'application/pdf')),
            byte_size INTEGER NOT NULL CHECK (byte_size > 0),
            width INTEGER NOT NULL CHECK (width > 0),
            height INTEGER NOT NULL CHECK (height > 0),
            storage_name TEXT NOT NULL UNIQUE,
            ocr_status TEXT NOT NULL DEFAULT 'pending' CHECK (ocr_status IN ('pending', 'processing', 'completed', 'partial', 'failed')),
            ocr_text TEXT,
            ocr_confidence REAL,
            question_text TEXT,
            solution_json TEXT,
            solved_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT,
            user_message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
            page_count INTEGER,
            page_results_json TEXT,
            failed_pages_json TEXT NOT NULL DEFAULT '[]',
            error_code TEXT
        );
        INSERT INTO attachments_v6
        SELECT id, user_id, conversation_id, original_name, media_type, byte_size, width, height,
               storage_name, ocr_status, ocr_text, ocr_confidence, question_text, solution_json,
               solved_at, created_at, updated_at, deleted_at, user_message_id,
               NULL, NULL, '[]', NULL
        FROM attachments;
        DROP TABLE attachments;
        ALTER TABLE attachments_v6 RENAME TO attachments;
        CREATE INDEX ix_attachments_user ON attachments(user_id, created_at);
        CREATE INDEX ix_attachments_conversation ON attachments(conversation_id, created_at);
        PRAGMA foreign_keys = ON;
        """,
    ),
    Migration(
        version=7,
        name="user_avatar",
        sql="ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT NULL;",
    ),
    Migration(version=8, name="quiz_bank", sql=QUIZ_SCHEMA),
    Migration(
        version=9,
        name="question_answer_variants",
        sql=(
            "ALTER TABLE questions ADD COLUMN accept_json TEXT;"
            "ALTER TABLE questions ADD COLUMN unordered INTEGER NOT NULL DEFAULT 0;"
        ),
    ),
    Migration(version=10, name="learning_loop", sql=LEARNING_LOOP_SCHEMA),
    Migration(version=11, name="student_grade", sql=STUDENT_GRADE_SCHEMA),
    Migration(version=12, name="attachment_dedupe", sql=ATTACHMENT_DEDUPE_SCHEMA),
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
