"""附件压缩、SHA-256 去重、共享文件删除与配额。"""

import io
import os

import pytest

from src import attachment_service
from src import db as db_module
from src.errors import ApiError
from src.schema import apply_migrations
from src.security import now_utc

Image = pytest.importorskip("PIL.Image")


@pytest.fixture
def attachment_env(tmp_path, monkeypatch):
    db_path = tmp_path / "attachments.db"
    conn = db_module.connect(db_path)
    apply_migrations(conn)
    now = now_utc()
    with conn:
        for uid in ("u1", "u2"):
            conn.execute(
                "INSERT INTO users (id, username, display_name, password_hash, role, status, "
                "created_at, updated_at) VALUES (?, ?, ?, 'x', 'student', 'active', ?, ?)",
                (uid, uid, uid, now, now),
            )
    storage = tmp_path / "storage"
    storage.mkdir()
    monkeypatch.setattr(attachment_service, "_STORAGE_ROOT", storage)
    yield conn, storage
    conn.close()


def _jpeg(width=1800, height=1200, quality=90, random=True) -> bytes:
    image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def test_compresses_large_image_and_records_original_size(attachment_env):
    conn, storage = attachment_env
    data = _jpeg(1800, 1200, quality=92)

    row = attachment_service.create(conn, "u1", data, "big.jpg", None)

    assert row["media_type"] == "image/jpeg"
    assert row["width"] <= 1600 and row["height"] <= 1600
    assert row["byte_size"] < len(data)
    assert row["original_byte_size"] == len(data)
    assert row["sha256"]
    assert (storage / row["storage_name"]).exists()


def test_same_content_shares_one_file_until_last_row_deleted(attachment_env):
    conn, storage = attachment_env
    data = _jpeg(1200, 900, quality=90)

    first = attachment_service.create(conn, "u1", data, "a.jpg", None)
    second = attachment_service.create(conn, "u1", data, "b.jpg", None)

    assert first["storage_name"] == second["storage_name"]
    assert first["sha256"] == second["sha256"]
    assert len(list(storage.iterdir())) == 1

    attachment_service.remove(conn, "u1", first["id"])
    assert (storage / first["storage_name"]).exists()

    attachment_service.remove(conn, "u1", second["id"])
    assert not (storage / first["storage_name"]).exists()


def test_dedupe_across_users_keeps_file_until_no_active_rows(attachment_env):
    conn, storage = attachment_env
    data = _jpeg(1000, 800, quality=88)

    first = attachment_service.create(conn, "u1", data, "a.jpg", None)
    second = attachment_service.create(conn, "u2", data, "b.jpg", None)
    assert first["storage_name"] == second["storage_name"]
    assert len(list(storage.iterdir())) == 1

    attachment_service.remove(conn, "u1", first["id"])
    assert (storage / first["storage_name"]).exists()

    attachment_service.remove(conn, "u2", second["id"])
    assert not (storage / first["storage_name"]).exists()


def test_quota_rejects_new_file(attachment_env, monkeypatch):
    conn, storage = attachment_env
    monkeypatch.setenv("IKGR_ATTACHMENT_QUOTA_BYTES", "1")
    data = _jpeg(800, 600, quality=85)

    with pytest.raises(ApiError) as exc:
        attachment_service.create(conn, "u1", data, "big.jpg", None)
    assert exc.value.code == "ATTACHMENT_QUOTA_EXCEEDED"
    assert list(storage.iterdir()) == []


def test_quota_does_not_double_count_same_file(attachment_env, monkeypatch):
    conn, storage = attachment_env
    data = _jpeg(800, 600, quality=85)

    first = attachment_service.create(conn, "u1", data, "a.jpg", None)
    used = first["byte_size"]
    monkeypatch.setenv("IKGR_ATTACHMENT_QUOTA_BYTES", str(used))

    # 同一用户再次上传同一内容不应因为配额被拒绝。
    second = attachment_service.create(conn, "u1", data, "b.jpg", None)
    assert second["storage_name"] == first["storage_name"]
    assert len(list(storage.iterdir())) == 1
