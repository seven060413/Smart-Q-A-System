"""数据库建表 / 迁移命令行入口（阶段 2）。

用法（在项目根目录执行）：
    .venv/Scripts/python.exe scripts/migrate.py           # 应用所有未执行的迁移
    .venv/Scripts/python.exe scripts/migrate.py status    # 查看已应用/待应用版本
    .venv/Scripts/python.exe scripts/migrate.py --db <路径>  # 指定数据库文件

迁移前会对已有数据库文件做在线快照（data/app/backups/），失败可回滚。
重复执行安全：已应用的版本会被跳过。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# 让脚本能直接以 `python scripts/migrate.py` 方式运行（不依赖包安装）。
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.schema import MIGRATIONS, apply_migrations, applied_versions  # noqa: E402


def _configure_stdout() -> None:
    """让中文输出不随 Windows 控制台 GBK 编码而乱码。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _backup_dir() -> Path:
    return db_module.resolve_db_path().parent / "backups"


def _snapshot(conn) -> Path | None:
    """迁移前若数据库文件已存在且有表，则做在线快照；新库/内存库跳过。"""
    path = db_module.resolve_db_path()
    if str(path) == ":memory:":
        return None
    has_tables = conn.execute(
        "SELECT COUNT(*) AS c FROM sqlite_master WHERE type='table' AND name != 'schema_migrations'"
    ).fetchone()["c"] > 0
    if not has_tables:
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = _backup_dir() / f"ikgr_before_migration_{ts}.db"
    return db_module.backup(conn, dest)


def run_migrate(db_path: str | None) -> None:
    conn = db_module.connect(db_path)
    try:
        pending = [m for m in sorted(MIGRATIONS, key=lambda x: x.version)
                   if m.version not in applied_versions(conn)]
        if not pending:
            print("无待应用的迁移，数据库已是最新。")
            return
        snapshot = _snapshot(conn)
        if snapshot:
            print(f"已创建迁移前快照: {snapshot}")
        applied = apply_migrations(conn, MIGRATIONS)
        print(f"本次应用 {len(applied)} 个迁移:")
        for m in applied:
            print(f"  - [{m.version}] {m.name}")
    finally:
        conn.close()


def run_status(db_path: str | None) -> None:
    conn = db_module.connect(db_path)
    try:
        done = applied_versions(conn)
        for m in sorted(MIGRATIONS, key=lambda x: x.version):
            mark = "已应用" if m.version in done else "待应用"
            print(f"[{m.version}] {m.name}: {mark}")
    finally:
        conn.close()


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="数据库建表 / 迁移")
    parser.add_argument("command", nargs="?", default="up", choices=["up", "status"],
                        help="up=应用迁移（默认），status=查看版本状态")
    parser.add_argument("--db", dest="db_path", default=None,
                        help="数据库文件路径（默认 data/app/ikgr.db，可用 IKGR_DB_PATH 覆盖）")
    args = parser.parse_args()

    if args.command == "status":
        run_status(args.db_path)
    else:
        run_migrate(args.db_path)


if __name__ == "__main__":
    main()
