"""v12 附件去重迁移：保留旧数据并移除 storage_name 唯一约束。"""

from src import db as db_module
from src.schema import MIGRATIONS, apply_migrations
from src.security import now_utc


def test_v12_preserves_rows_and_allows_shared_storage_name():
    conn = db_module.connect(":memory:")
    try:
        apply_migrations(conn, MIGRATIONS[:-1])  # v1-v11
        now = now_utc()
        with conn:
            conn.execute(
                "INSERT INTO users (id, username, display_name, password_hash, role, status, "
                "created_at, updated_at) VALUES ('u1', 'u1', 'u1', 'x', 'student', 'active', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO attachments "
                "(id, user_id, original_name, media_type, byte_size, width, height, "
                " storage_name, created_at, updated_at) "
                "VALUES ('a1', 'u1', 'x.jpg', 'image/jpeg', 3, 1, 1, 'same.bin', ?, ?)",
                (now, now),
            )

        applied = apply_migrations(conn, MIGRATIONS[-1:])
        assert [m.version for m in applied] == [12]

        columns = {row[1] for row in conn.execute("PRAGMA table_info(attachments)")}
        assert {"sha256", "original_byte_size"} <= columns
        row = conn.execute("SELECT * FROM attachments WHERE id = 'a1'").fetchone()
        assert row["storage_name"] == "same.bin"
        assert row["sha256"] is None
        assert row["original_byte_size"] is None

        # storage_name 不再 UNIQUE：同一文件可以被多条记录引用。
        with conn:
            conn.execute(
                "INSERT INTO attachments "
                "(id, user_id, original_name, media_type, byte_size, width, height, "
                " storage_name, created_at, updated_at) "
                "VALUES ('a2', 'u1', 'y.jpg', 'image/jpeg', 3, 1, 1, 'same.bin', ?, ?)",
                (now, now),
            )
        assert conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0] == 2
    finally:
        conn.close()
