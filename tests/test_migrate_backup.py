"""迁移快照保留策略测试。"""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate.py"


def _load_migrate_module():
    spec = importlib.util.spec_from_file_location("migrate_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prune_only_migration_snapshots(tmp_path):
    module = _load_migrate_module()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
        (backup_dir / f"ikgr_before_migration_{stamp}.db").write_bytes(b"db")
    deploy = backup_dir / "ikgr_before_deploy_20260101.db"
    data = backup_dir / "ikgr_data_20260101T000000Z.tar.gz"
    deploy.write_bytes(b"x")
    data.write_bytes(b"x")

    removed = module._prune_migration_backups(backup_dir, keep=2)

    remaining = sorted(p.name for p in backup_dir.iterdir())
    assert [p.name for p in removed] == ["ikgr_before_migration_20260101T000000Z.db"]
    assert remaining == [
        "ikgr_before_deploy_20260101.db",
        "ikgr_before_migration_20260102T000000Z.db",
        "ikgr_before_migration_20260103T000000Z.db",
        "ikgr_data_20260101T000000Z.tar.gz",
    ]


def test_keep_zero_does_not_prune(tmp_path):
    module = _load_migrate_module()
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for stamp in ("20260101T000000Z", "20260102T000000Z"):
        (backup_dir / f"ikgr_before_migration_{stamp}.db").write_bytes(b"db")

    assert module._prune_migration_backups(backup_dir, keep=0) == []
    assert len(list(backup_dir.iterdir())) == 2
