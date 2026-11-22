"""历史附件 sha256 回填与旧重复文件合并。"""

import importlib.util
from pathlib import Path

from src import db as db_module
from src.schema import apply_migrations
from src.security import now_utc

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_attachment_sha.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("backfill_attachment_sha", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed(tmp_path):
    db_path = tmp_path / "attachments.db"
    storage = tmp_path / "storage"
    storage.mkdir()
    payload = b"same-content"
    (storage / "a.bin").write_bytes(payload)
    (storage / "b.bin").write_bytes(payload)

    conn = db_module.connect(db_path)
    apply_migrations(conn)
    now = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO users (id, username, display_name, password_hash, role, status, "
            "created_at, updated_at) VALUES ('u1', 'u1', 'u1', 'x', 'student', 'active', ?, ?)",
            (now, now),
        )
        for aid, name in (("a1", "a.bin"), ("a2", "b.bin")):
            conn.execute(
                "INSERT INTO attachments "
                "(id, user_id, original_name, media_type, byte_size, width, height, "
                " storage_name, created_at, updated_at) "
                "VALUES (?, 'u1', 'x.jpg', 'image/jpeg', ?, 1, 1, ?, ?, ?)",
                (aid, len(payload), name, now, now),
            )
    conn.close()
    return db_path, storage


def test_dry_run_does_not_write(tmp_path):
    module = _load_module()
    db_path, storage = _seed(tmp_path)

    stats = module.backfill(
        db_path=db_path, attachments_dir=storage, apply=False, dedupe=False
    )
    assert stats["hashed_files"] == 2
    assert stats["hashed_rows"] == 0

    conn = db_module.connect(db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM attachments WHERE sha256 IS NOT NULL"
        ).fetchone()[0] == 0
    finally:
        conn.close()
    assert len(list(storage.iterdir())) == 2


def test_apply_backfills_and_merges_duplicate_files(tmp_path):
    module = _load_module()
    db_path, storage = _seed(tmp_path)

    stats = module.backfill(
        db_path=db_path, attachments_dir=storage, apply=True, dedupe=True
    )
    assert stats["hashed_files"] == 2
    assert stats["hashed_rows"] == 2
    assert stats["deduped_groups"] == 1
    assert stats["deduped_rows"] == 1
    assert stats["removed_files"] == 1

    conn = db_module.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT storage_name, sha256 FROM attachments ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    assert {row["storage_name"] for row in rows} == {"a.bin"}
    assert len({row["sha256"] for row in rows}) == 1
    assert sorted(p.name for p in storage.iterdir()) == ["a.bin"]
