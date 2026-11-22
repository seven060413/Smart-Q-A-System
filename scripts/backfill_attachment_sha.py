"""为历史附件补齐 sha256，并可选合并内容重复的旧文件。

背景：v12 之前 attachments 没有 sha256，且 storage_name 是 UNIQUE。
新上传已经按内容去重；这个脚本用于一次性处理历史文件。

默认 dry-run，只统计不修改。确认后加 --apply：
    .venv/Scripts/python.exe scripts/backfill_attachment_sha.py
    .venv/Scripts/python.exe scripts/backfill_attachment_sha.py --apply --dedupe
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _hash_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def backfill(
    *,
    db_path: str | Path | None = None,
    attachments_dir: str | Path | None = None,
    apply: bool = False,
    dedupe: bool = False,
) -> dict:
    resolved_db = db_module.resolve_db_path(db_path)
    if not resolved_db.exists():
        raise FileNotFoundError(f"数据库不存在：{resolved_db}")

    if attachments_dir is None:
        from src.attachment_service import storage_root

        storage = storage_root()
    else:
        storage = Path(attachments_dir)

    conn = db_module.connect(resolved_db)
    stats = {
        "hashed_files": 0,
        "hashed_rows": 0,
        "deduped_groups": 0,
        "deduped_rows": 0,
        "removed_files": 0,
    }
    try:
        rows = conn.execute(
            "SELECT DISTINCT storage_name FROM attachments WHERE sha256 IS NULL"
        ).fetchall()
        hashes: dict[str, str] = {}
        for row in rows:
            name = row["storage_name"]
            digest = _hash_file(storage / name)
            if digest is None:
                continue
            hashes[name] = digest
            stats["hashed_files"] += 1

        if apply and hashes:
            with conn:
                for name, digest in hashes.items():
                    cursor = conn.execute(
                        "UPDATE attachments SET sha256 = ?, "
                        "original_byte_size = COALESCE(original_byte_size, byte_size) "
                        "WHERE storage_name = ? AND sha256 IS NULL",
                        (digest, name),
                    )
                    stats["hashed_rows"] += cursor.rowcount

        if dedupe:
            groups = conn.execute(
                "SELECT sha256, media_type, COUNT(DISTINCT storage_name) AS files "
                "FROM attachments WHERE sha256 IS NOT NULL AND deleted_at IS NULL "
                "GROUP BY sha256, media_type HAVING files > 1"
            ).fetchall()
            stats["deduped_groups"] = len(groups)
            for group in groups:
                names = [
                    row["storage_name"]
                    for row in conn.execute(
                        "SELECT DISTINCT storage_name FROM attachments "
                        "WHERE sha256 = ? AND media_type = ? AND deleted_at IS NULL",
                        (group["sha256"], group["media_type"]),
                    )
                ]
                canonical = min(
                    names, key=lambda name: (not (storage / name).exists(), name)
                )
                count = conn.execute(
                    "SELECT COUNT(*) FROM attachments "
                    "WHERE sha256 = ? AND media_type = ? AND deleted_at IS NULL "
                    "AND storage_name <> ?",
                    (group["sha256"], group["media_type"], canonical),
                ).fetchone()[0]
                stats["deduped_rows"] += int(count)
                if apply:
                    with conn:
                        conn.execute(
                            "UPDATE attachments SET storage_name = ? "
                            "WHERE sha256 = ? AND media_type = ? AND deleted_at IS NULL",
                            (canonical, group["sha256"], group["media_type"]),
                        )

            if apply:
                active = {
                    row["storage_name"]
                    for row in conn.execute(
                        "SELECT DISTINCT storage_name FROM attachments WHERE deleted_at IS NULL"
                    )
                }
                for path in (storage.iterdir() if storage.exists() else []):
                    if path.is_file() and path.name not in active:
                        try:
                            path.unlink()
                            stats["removed_files"] += 1
                        except OSError:
                            pass
    finally:
        conn.close()
    return stats


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="回填附件 sha256 / 合并旧重复文件")
    parser.add_argument("--db", default=None, help="数据库路径（默认 data/app/ikgr.db）")
    parser.add_argument("--attachments", default=None, help="附件目录")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认 dry-run")
    parser.add_argument("--dedupe", action="store_true", help="合并 sha256 相同的旧文件")
    args = parser.parse_args()

    stats = backfill(
        db_path=args.db,
        attachments_dir=args.attachments,
        apply=args.apply,
        dedupe=args.dedupe,
    )
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] 附件哈希回填/去重")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
