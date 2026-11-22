"""清理服务端不再需要的数据。

默认只做低风险清理：
- 已过期的登录会话（auth_sessions）；
- 超过 --days 天的已完成诊断会话（quiz_sessions，级联删除 quiz_attempts）；
- 超过 --days 天前软删除的会话（conversations，级联删除 messages）；
- 超过 --days 天前软删除的附件记录（attachments）。

可选 --orphans 清理磁盘上没有任何附件行引用的文件（默认跳过 1 小时内
新写入的文件，避免和正在进行的上传竞争）。

建议在服务停止或低峰期执行；先加 --dry-run 看数量。

用法：
    .venv/Scripts/python.exe scripts/cleanup_data.py --dry-run
    .venv/Scripts/python.exe scripts/cleanup_data.py --days 365
    .venv/Scripts/python.exe scripts/cleanup_data.py --days 365 --orphans
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402

ORPHAN_MIN_AGE_SECONDS = 3600


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _iso_days_ago(days: int) -> str:
    value = datetime.now(timezone.utc) - timedelta(days=days)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _count(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0] if row else 0)


def _orphan_files(conn, storage_root: Path) -> list[Path]:
    if not storage_root.exists():
        return []
    referenced = {
        row["storage_name"]
        for row in conn.execute("SELECT DISTINCT storage_name FROM attachments")
    }
    now = time.time()
    orphans = []
    for path in storage_root.iterdir():
        if not path.is_file() or path.name in referenced:
            continue
        try:
            if now - path.stat().st_mtime < ORPHAN_MIN_AGE_SECONDS:
                continue
        except OSError:
            continue
        orphans.append(path)
    return orphans


def cleanup(
    *,
    db_path: str | Path | None = None,
    days: int = 365,
    dry_run: bool = False,
    orphans: bool = False,
    attachments_dir: str | Path | None = None,
) -> dict:
    """执行清理，返回各类数量统计。"""
    resolved_db = db_module.resolve_db_path(db_path)
    if not resolved_db.exists():
        raise FileNotFoundError(f"数据库不存在：{resolved_db}")

    if attachments_dir is None:
        from src.attachment_service import storage_root

        resolved_attachments = storage_root()
    else:
        resolved_attachments = Path(attachments_dir)

    cutoff = _iso_days_ago(days)
    now = _now_iso()
    conn = db_module.connect(resolved_db)
    stats: dict[str, int] = {}
    try:
        stats["auth_sessions"] = _count(
            conn, "SELECT COUNT(*) FROM auth_sessions WHERE expires_at < ?", (now,)
        )
        stats["quiz_sessions"] = _count(
            conn,
            "SELECT COUNT(*) FROM quiz_sessions "
            "WHERE user_id IS NOT NULL AND status = 'completed' AND created_at < ?",
            (cutoff,),
        )
        stats["quiz_attempts"] = _count(
            conn,
            "SELECT COUNT(*) FROM quiz_attempts a JOIN quiz_sessions s ON s.id = a.session_id "
            "WHERE s.user_id IS NOT NULL AND s.status = 'completed' AND s.created_at < ?",
            (cutoff,),
        )
        stats["conversations"] = _count(
            conn,
            "SELECT COUNT(*) FROM conversations WHERE deleted_at IS NOT NULL AND deleted_at < ?",
            (cutoff,),
        )
        stats["messages"] = _count(
            conn,
            "SELECT COUNT(*) FROM messages WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE deleted_at IS NOT NULL AND deleted_at < ?)",
            (cutoff,),
        )
        stats["attachments_soft_deleted"] = _count(
            conn,
            "SELECT COUNT(*) FROM attachments WHERE deleted_at IS NOT NULL AND deleted_at < ?",
            (cutoff,),
        )
        stats["attachments_in_deleted_conversations"] = _count(
            conn,
            "SELECT COUNT(*) FROM attachments WHERE conversation_id IN "
            "(SELECT id FROM conversations WHERE deleted_at IS NOT NULL AND deleted_at < ?)",
            (cutoff,),
        )
        orphan_paths = _orphan_files(conn, resolved_attachments) if orphans else []
        stats["orphan_files"] = len(orphan_paths)
        stats["orphan_bytes"] = sum(p.stat().st_size for p in orphan_paths)

        if dry_run:
            return stats

        with conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE expires_at < ?", (now,)
            )
            conn.execute(
                "DELETE FROM attachments WHERE conversation_id IN "
                "(SELECT id FROM conversations WHERE deleted_at IS NOT NULL AND deleted_at < ?)",
                (cutoff,),
            )
            conn.execute(
                "DELETE FROM attachments WHERE deleted_at IS NOT NULL AND deleted_at < ?",
                (cutoff,),
            )
            conn.execute(
                "DELETE FROM conversations WHERE deleted_at IS NOT NULL AND deleted_at < ?",
                (cutoff,),
            )
            conn.execute(
                "DELETE FROM quiz_sessions "
                "WHERE user_id IS NOT NULL AND status = 'completed' AND created_at < ?",
                (cutoff,),
            )

        # 附件行删除后，再清理不再被任何行引用的文件。
        if orphans:
            for path in _orphan_files(conn, resolved_attachments):
                try:
                    path.unlink()
                except OSError:
                    pass
    finally:
        conn.close()

    return stats


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="清理过期/软删除数据")
    parser.add_argument("--db", default=None, help="数据库路径（默认 data/app/ikgr.db）")
    parser.add_argument("--days", type=int, default=365, help="诊断/会话/附件保留天数，默认 365")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不删除")
    parser.add_argument("--orphans", action="store_true", help="同时清理无引用的附件文件")
    parser.add_argument("--attachments", default=None, help="附件目录（默认 data/app/attachments）")
    args = parser.parse_args()

    try:
        stats = cleanup(
            db_path=args.db,
            days=max(1, args.days),
            dry_run=args.dry_run,
            orphans=args.orphans,
            attachments_dir=args.attachments,
        )
    except Exception as exc:
        print(f"清理失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    mode = "DRY-RUN" if args.dry_run else "DONE"
    print(f"[{mode}] 保留 {args.days} 天")
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
