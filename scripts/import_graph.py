"""课程图谱导入命令行入口（阶段 2）。

用法（在项目根目录执行）：
    # 导入全量数学图谱（subject_full）
    .venv/Scripts/python.exe scripts/import_graph.py \
        --json data/raw/math.json --scope subject_full

    # 导入五年级下册子图（book）
    .venv/Scripts/python.exe scripts/import_graph.py \
        --json data/processed/math_5b_knowledge_graph.json --scope book --book-id math_5b_rjb

    # 强制重新导入（源文件内容变化后）
    .venv/Scripts/python.exe scripts/import_graph.py --json data/raw/math.json --scope subject_full --force

重复执行安全：同一版本且源文件未变化时跳过；内容变化需显式 --force。
原始 JSON 只读，绝不删除、不覆盖。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.graph_import import delete_version, import_graph  # noqa: E402


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _print_report(report) -> None:
    print("=" * 60)
    if report.skipped:
        print(f"已跳过（版本 {report.version_id} 已存在且内容一致）")
        print(f"  源文件: {report.source_path}")
        print(f"  SHA-256: {report.source_sha256}")
        print("=" * 60)
        return
    print(f"导入完成 版本: {report.version_id}")
    print(f"  源文件: {report.source_path}")
    print(f"  SHA-256: {report.source_sha256}")
    print(f"  节点: {report.node_count}")
    print(f"  边: {report.edge_count}（标量 {report.scalar_edge_count} + 列表目标 {report.special_edge_count}）")
    print(f"  边目标行: {report.target_row_count}")
    print(f"  节点类型: {report.node_label_counts}")
    print(f"  边类型: {report.edge_type_counts}")
    if report.missing_target_edges:
        print(f"  [警告] 既无 target 也无 target_name_to_ids 的边: {report.missing_target_edges}")
    if report.orphan_source_edges:
        print(f"  [警告] 源节点缺失的边: {report.orphan_source_edges}")
    if report.orphan_target_rows:
        print(f"  [警告] 目标节点缺失的目标行: {report.orphan_target_rows}")
    print("=" * 60)


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="导入/删除课程图谱 JSON 数据（SQLite）")
    parser.add_argument("--json", dest="json_path", default=None, help="图谱 JSON 路径（导入时必填）")
    parser.add_argument("--scope", default="subject_full",
                        choices=["subject_full", "book", "custom"],
                        help="版本范围：subject_full=全学科，book=某册")
    parser.add_argument("--book-id", dest="book_id", default=None,
                        help="scope=book 时的教材册 id（如 math_5b_rjb）")
    parser.add_argument("--course-id", dest="course_id", default="math")
    parser.add_argument("--course-name", dest="course_name", default="小学数学")
    parser.add_argument("--subject", default="math")
    parser.add_argument("--dataset-name", dest="dataset_name", default=None,
                        help="数据集名称（默认按范围生成）")
    parser.add_argument("--dataset-version", dest="dataset_version", default=None)
    parser.add_argument("--force", action="store_true", help="源文件变化后强制重导")
    parser.add_argument("--inactive", action="store_true", help="导入为未启用版本")
    parser.add_argument("--delete-version", dest="delete_version_id", default=None,
                        help="删除指定图谱版本及其数据（如 math:book:math_5b_rjb）")
    parser.add_argument("--db", dest="db_path", default=None,
                        help="数据库文件路径（默认 data/app/ikgr.db）")
    args = parser.parse_args()

    # —— 删除模式：不需要 --json ——
    if args.delete_version_id:
        conn = db_module.connect(args.db_path)
        try:
            before = delete_version(conn, args.delete_version_id)
            if not before["exists"]:
                print(f"版本 {args.delete_version_id} 不存在，无需删除。")
            else:
                print("=" * 60)
                print(f"已删除版本: {before['version_id']}")
                print(f"  删除前: 节点 {before['nodes']}，边 {before['edges']}，边目标行 {before['targets']}")
                print("  原始 JSON 文件未受影响。")
                print("=" * 60)
        finally:
            conn.close()
        return

    # —— 导入模式 ——
    if not args.json_path:
        parser.error("导入需要 --json <路径>；或使用 --delete-version <版本id> 删除已有版本")
    if args.scope == "book" and not args.book_id:
        parser.error("--scope book 需要 --book-id")

    dataset_name = args.dataset_name
    if dataset_name is None:
        dataset_name = (
            f"K12-KGraph math ({args.book_id})" if args.scope == "book"
            else "K12-KGraph math"
        )

    conn = db_module.connect(args.db_path)
    try:
        report = import_graph(
            conn,
            args.json_path,
            course_id=args.course_id,
            course_name=args.course_name,
            subject=args.subject,
            scope=args.scope,
            book_id=args.book_id,
            dataset_name=dataset_name,
            dataset_version=args.dataset_version,
            force=args.force,
            make_active=not args.inactive,
        )
        _print_report(report)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
