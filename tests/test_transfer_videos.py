"""视频库数据包导出/导入测试。"""

import importlib.util
import json
from pathlib import Path

import pytest

from src import db as db_module
from src.schema import MIGRATIONS, apply_migrations
from src.security import now_utc

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "transfer_videos.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("transfer_videos_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_source(path):
    conn = db_module.connect(path)
    apply_migrations(conn, MIGRATIONS)
    now = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO courses (id, code, name, subject, status, created_at, updated_at) "
            "VALUES ('math', 'math', '数学', 'math', 'active', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO videos (id, platform, bvid, page, title, watch_url, status, "
            "metadata_json, created_at, updated_at) "
            "VALUES ('v1', 'bilibili', 'BV1', 1, '视频一', "
            "'https://www.bilibili.com/video/BV1', 'active', '{}', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO knowledge_point_videos "
            "(course_id, node_key, node_name, video_id, relation, rank, review_status, "
            " reviewed_by, reviewed_at, created_at, updated_at) "
            "VALUES ('math', 'n1', '知识点一', 'v1', 'explains', 1, 'approved', "
            "'tester', ?, ?, ?)",
            (now, now, now),
        )
    conn.close()


def _prepare_target(path):
    conn = db_module.connect(path)
    apply_migrations(conn, MIGRATIONS)
    now = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO courses (id, code, name, subject, status, created_at, updated_at) "
            "VALUES ('math', 'math', '数学', 'math', 'active', ?, ?)",
            (now, now),
        )
    conn.close()


def _counts(path):
    conn = db_module.connect(path)
    try:
        videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        mappings = conn.execute(
            "SELECT COUNT(*) FROM knowledge_point_videos"
        ).fetchone()[0]
        return videos, mappings
    finally:
        conn.close()


def test_export_import_is_idempotent(tmp_path):
    module = _load_module()
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    pack = tmp_path / "videos.json"
    _prepare_source(source)
    _prepare_target(target)

    payload = module.export_pack(str(source), str(pack))
    assert payload["counts"] == {"videos": 1, "mappings": 1}
    assert pack.exists()

    dry = module.import_pack(str(target), str(pack))
    assert dry["applied"] is False
    assert _counts(target) == (0, 0)

    first = module.import_pack(str(target), str(pack), apply=True)
    assert first["new_videos"] == 1
    assert first["new_mappings"] == 1
    assert _counts(target) == (1, 1)
    assert list((target.parent / "backups").glob("ikgr_before_videos_import_*.db"))

    second = module.import_pack(str(target), str(pack), apply=True)
    assert second["new_videos"] == 0
    assert second["new_mappings"] == 0
    assert _counts(target) == (1, 1)


def test_import_updates_existing_rows(tmp_path):
    module = _load_module()
    source = tmp_path / "source.db"
    target = tmp_path / "target.db"
    pack = tmp_path / "videos.json"
    _prepare_source(source)
    _prepare_target(target)

    module.export_pack(str(source), str(pack))
    module.import_pack(str(target), str(pack), apply=True)

    data = json.loads(pack.read_text(encoding="utf-8"))
    data["videos"][0]["title"] = "改名后的视频"
    data["mappings"][0]["rank"] = 3
    pack.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result = module.import_pack(str(target), str(pack), apply=True)
    assert result["new_videos"] == 0
    assert _counts(target) == (1, 1)

    conn = db_module.connect(target)
    try:
        assert conn.execute("SELECT title FROM videos").fetchone()[0] == "改名后的视频"
        assert conn.execute(
            "SELECT rank FROM knowledge_point_videos"
        ).fetchone()[0] == 3
    finally:
        conn.close()


def test_pack_rejects_mapping_with_unknown_video(tmp_path):
    module = _load_module()
    pack = tmp_path / "bad.json"
    pack.write_text(
        json.dumps(
            {
                "format_version": 1,
                "videos": [],
                "mappings": [{"video_id": "missing"}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(module.TransferError, match="不存在的视频"):
        module.load_pack(pack)
