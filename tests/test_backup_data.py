"""服务端数据备份脚本：DB + 附件 + .env + 保留策略。"""

import importlib.util
import json
import tarfile
from pathlib import Path

from src import db as db_module
from src.schema import apply_migrations

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_data.py"


def _load_backup_module():
    spec = importlib.util.spec_from_file_location("backup_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_db(db_path: Path) -> None:
    conn = db_module.connect(db_path)
    try:
        apply_migrations(conn)
    finally:
        conn.close()


def test_backup_contains_db_attachments_env_and_manifest(tmp_path, monkeypatch):
    module = _load_backup_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)

    db_path = tmp_path / "ikgr.db"
    _make_db(db_path)
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "abc.bin").write_bytes(b"hello-image")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    archive_path = module.create_backup(
        db_path=db_path,
        out_dir=tmp_path / "backups",
        attachments_dir=attachments,
        keep=7,
        include_env=True,
        timestamp="20260101T000000Z",
    )

    assert archive_path.exists()
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
        assert "ikgr_data/ikgr.db" in names
        assert "ikgr_data/attachments/abc.bin" in names
        assert "ikgr_data/.env" in names
        assert "ikgr_data/manifest.json" in names

        raw_manifest = archive.extractfile("ikgr_data/manifest.json").read()
        manifest = json.loads(raw_manifest.decode("utf-8"))
    assert manifest["attachments"]["files"] == 1
    assert manifest["attachments"]["bytes"] == len(b"hello-image")
    assert manifest["includes_env"] is True


def test_backup_keeps_only_latest_n_archives(tmp_path, monkeypatch):
    module = _load_backup_module()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    db_path = tmp_path / "ikgr.db"
    _make_db(db_path)
    out_dir = tmp_path / "backups"

    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        module.create_backup(
            db_path=db_path,
            out_dir=out_dir,
            attachments_dir=tmp_path / "missing-attachments",
            keep=2,
            include_env=False,
            timestamp=stamp,
        )

    names = sorted(p.name for p in out_dir.glob("ikgr_data_*.tar.gz"))
    assert names == [
        "ikgr_data_20260102T000000Z.tar.gz",
        "ikgr_data_20260103T000000Z.tar.gz",
    ]
