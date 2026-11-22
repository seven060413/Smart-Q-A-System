"""备份服务端数据：SQLite + 附件文件 + .env。

为什么不能只备份 ikgr.db：
- 附件表只存文件名，真实图片/PDF 在 data/app/attachments；
- .env 里有数据库路径、模型/ASR 等配置，重建服务器时同样需要；
- 直接复制正在写入的 .db 可能拿到半写状态，这里用 SQLite 在线备份 API。

用法（在项目根目录执行）：
    .venv/Scripts/python.exe scripts/backup_data.py
    .venv/Scripts/python.exe scripts/backup_data.py --keep 7
    .venv/Scripts/python.exe scripts/backup_data.py --db data/app/ikgr.db --out data/app/backups
    .venv/Scripts/python.exe scripts/backup_data.py --attachments data/app/attachments

产物：ikgr_data_<UTC时间戳>.tar.gz，内含：
    ikgr_data/ikgr.db
    ikgr_data/attachments/...
    ikgr_data/.env
    ikgr_data/manifest.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402

ARCHIVE_PREFIX = "ikgr_data_"
ARCHIVE_SUFFIX = ".tar.gz"


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _dir_stats(path: Path) -> tuple[int, int]:
    files = 0
    total = 0
    if not path.exists():
        return files, total
    for item in path.rglob("*"):
        if item.is_file():
            files += 1
            total += item.stat().st_size
    return files, total


def _prune(out_dir: Path, keep: int) -> list[Path]:
    """只清理本脚本生成的备份，保留最近 keep 份。"""
    if keep <= 0:
        return []
    backups = sorted(
        out_dir.glob(f"{ARCHIVE_PREFIX}*{ARCHIVE_SUFFIX}"),
        key=lambda p: p.name,
        reverse=True,
    )
    removed = []
    for old in backups[keep:]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            pass
    return removed


def create_backup(
    *,
    db_path: str | Path | None = None,
    out_dir: str | Path | None = None,
    attachments_dir: str | Path | None = None,
    keep: int = 7,
    include_env: bool = True,
    timestamp: str | None = None,
) -> Path:
    """创建一份数据备份，返回归档路径。"""
    resolved_db = db_module.resolve_db_path(db_path)
    if not resolved_db.exists():
        raise FileNotFoundError(f"数据库不存在：{resolved_db}")

    resolved_out = Path(out_dir) if out_dir else resolved_db.parent / "backups"
    resolved_out.mkdir(parents=True, exist_ok=True)

    if attachments_dir is None:
        # 延迟导入，避免脚本在没装图片依赖时启动失败。
        from src.attachment_service import storage_root

        resolved_attachments = storage_root()
    else:
        resolved_attachments = Path(attachments_dir)

    stamp = timestamp or _timestamp()
    dest = resolved_out / f"{ARCHIVE_PREFIX}{stamp}{ARCHIVE_SUFFIX}"
    if dest.exists():
        raise FileExistsError(f"备份已存在：{dest}")

    temp_dir = resolved_out / f".tmp_{stamp}"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    try:
        temp_dir.chmod(0o700)
    except OSError:
        pass

    try:
        # 1) SQLite 在线快照：不复制 .db-wal/.db-shm，保证一致性。
        source = db_module.connect(resolved_db)
        try:
            db_module.backup(source, temp_dir / "ikgr.db")
        finally:
            source.close()

        # 2) 附件文件
        attachment_files, attachment_bytes = _dir_stats(resolved_attachments)
        if resolved_attachments.exists() and attachment_files:
            shutil.copytree(resolved_attachments, temp_dir / "attachments")

        # 3) .env（可选）
        env_copied = False
        env_path = ROOT / ".env"
        if include_env and env_path.exists():
            shutil.copy2(env_path, temp_dir / ".env")
            env_copied = True

        manifest = {
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "database": "ikgr.db",
            "attachments": {
                "files": attachment_files,
                "bytes": attachment_bytes,
            },
            "includes_env": env_copied,
        }
        (temp_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 4) 打包；归档含 .env，尽量收紧权限。
        with tarfile.open(dest, "w:gz") as archive:
            archive.add(temp_dir, arcname="ikgr_data")
        try:
            dest.chmod(0o600)
        except OSError:
            pass
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    else:
        shutil.rmtree(temp_dir, ignore_errors=True)

    _prune(resolved_out, keep)
    return dest


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="备份 IKGR 服务端数据")
    parser.add_argument("--db", default=None, help="数据库路径（默认 data/app/ikgr.db）")
    parser.add_argument("--out", default=None, help="备份目录（默认数据库旁的 backups/）")
    parser.add_argument("--attachments", default=None, help="附件目录（默认 data/app/attachments）")
    parser.add_argument("--keep", type=int, default=7, help="保留最近几份，默认 7；0 表示不清理")
    parser.add_argument("--no-env", action="store_true", help="不把 .env 打进备份")
    args = parser.parse_args()

    try:
        path = create_backup(
            db_path=args.db,
            out_dir=args.out,
            attachments_dir=args.attachments,
            keep=args.keep,
            include_env=not args.no_env,
        )
    except Exception as exc:
        print(f"备份失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    size = path.stat().st_size
    print(f"备份完成：{path}")
    print(f"归档大小：{size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
