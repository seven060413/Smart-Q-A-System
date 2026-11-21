"""把 pansgo 题库写入 questions 表（幂等）。

用法（项目根目录执行）：
    .venv/Scripts/python.exe scripts/seed_pansgo_questions.py
    .venv/Scripts/python.exe scripts/seed_pansgo_questions.py --db data/app/ikgr.db

先决条件：已运行 scripts/build_pansgo_graph.py 生成题库 JSON。
脚本会自动应用未执行的迁移（v8），重复执行只会更新同 id 的题目。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src import pansgo, quiz_service  # noqa: E402
from src.schema import MIGRATIONS, apply_migrations  # noqa: E402


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def main() -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="导入 pansgo 题库到 SQLite")
    parser.add_argument(
        "--questions",
        default=str(ROOT / "data" / "processed" / "pansgo_math_k12_questions.json"),
    )
    parser.add_argument("--db", default=None, help="数据库路径（默认 data/app/ikgr.db）")
    parser.add_argument("--dataset-version", default=pansgo.SOURCE_COMMIT)
    args = parser.parse_args()

    path = Path(args.questions)
    if not path.exists():
        print(f"找不到题库文件: {path}", file=sys.stderr)
        print("请先运行 scripts/build_pansgo_graph.py", file=sys.stderr)
        return 1

    payload = json.loads(path.read_text(encoding="utf-8"))
    questions = payload.get("questions", payload if isinstance(payload, list) else [])
    if not questions:
        print("题库为空。", file=sys.stderr)
        return 1

    conn = db_module.connect(args.db)
    try:
        apply_migrations(conn, MIGRATIONS)
        count = quiz_service.seed_questions(conn, questions, args.dataset_version)
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM questions WHERE dataset_version = ?",
            (args.dataset_version,),
        ).fetchone()["c"]
    finally:
        conn.close()

    print("=" * 60)
    print(f"题库文件: {path}")
    print(f"数据集版本: {args.dataset_version}")
    print(f"本次写入: {count} 条；库内该版本共 {total} 条")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
