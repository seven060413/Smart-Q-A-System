"""把抓取到的 cn-math-taxonomy 数学数据转成项目图谱 JSON、题库 JSON 与目录 JSON。

用法（项目根目录执行）：
    .venv/Scripts/python.exe scripts/build_pansgo_graph.py
    .venv/Scripts/python.exe scripts/build_pansgo_graph.py --input-dir data/raw/pansgo_k12
    .venv/Scripts/python.exe scripts/build_pansgo_graph.py --max-grade 14

输入（默认 data/raw/pansgo_k12/）：topics.json / dependencies.json / questions.json
输出：
    data/processed/pansgo_math_k12.json            图谱（nodes + edges）
    data/processed/pansgo_math_k12_questions.json  题库
    data/processed/pansgo_math_k12_catalog.json    年级 / 册 / 章 / 知识点目录

图谱格式与 data/raw/math.json 一致，可直接用 scripts/import_graph.py 导入：
    .venv/Scripts/python.exe scripts/import_graph.py \
        --json data/processed/pansgo_math_k12.json --scope custom --book-id pansgo_math_k12 \
        --course-id pansgo_math --course-name "数学（pansgo K12）"
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import pansgo  # noqa: E402
from src.graph import find_cycles  # noqa: E402


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _check_cycles(graph_payload) -> list:
    g = nx.DiGraph()
    for node in graph_payload["nodes"]:
        g.add_node(node["id"])
    for edge in graph_payload["edges"]:
        g.add_edge(edge["source"], edge["target"])
    return find_cycles(g)


def main() -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="构建 pansgo 数学 K12 图谱、题库与目录")
    parser.add_argument("--input-dir", default=str(ROOT / "data" / "raw" / "pansgo_k12"))
    parser.add_argument("--graph-out", default=str(ROOT / "data" / "processed" / "pansgo_math_k12.json"))
    parser.add_argument(
        "--questions-out",
        default=str(ROOT / "data" / "processed" / "pansgo_math_k12_questions.json"),
    )
    parser.add_argument(
        "--catalog-out",
        default=str(ROOT / "data" / "processed" / "pansgo_math_k12_catalog.json"),
    )
    parser.add_argument("--max-grade", type=int, default=pansgo.MAX_GRADE)
    args = parser.parse_args()

    in_dir = Path(args.input_dir)
    raw = {
        name: pansgo.load_json(in_dir / name)
        for name in ("topics.json", "dependencies.json", "questions.json")
    }
    filtered = pansgo.filter_math(
        raw["topics.json"], raw["dependencies.json"], raw["questions.json"],
        max_grade=args.max_grade,
    )
    errors = pansgo.validate(filtered)
    if errors:
        for error in errors[:20]:
            print(f"[错误] {error}", file=sys.stderr)
        print(f"数据校验失败，共 {len(errors)} 处问题。", file=sys.stderr)
        return 1

    graph_payload = pansgo.build_graph(
        filtered["topics"], filtered["dependencies"], max_grade=args.max_grade
    )
    bank_payload = pansgo.build_question_bank(filtered["questions"])
    catalog_payload = pansgo.build_catalog(filtered["topics"], filtered["questions"])

    cycles = _check_cycles(graph_payload)
    if cycles:
        print(f"[错误] 先修关系存在 {len(cycles)} 个环，例如: {cycles[:3]}", file=sys.stderr)
        return 1

    graph_path = Path(args.graph_out)
    questions_path = Path(args.questions_out)
    catalog_path = Path(args.catalog_out)
    graph_sha = pansgo.write_json(graph_path, graph_payload)
    questions_sha = pansgo.write_json(questions_path, bank_payload)
    catalog_sha = pansgo.write_json(catalog_path, catalog_payload)

    by_grade = Counter(t["grade"] for t in filtered["topics"])
    by_difficulty = Counter(q.get("difficulty") for q in filtered["questions"])
    by_type = Counter(q.get("type") for q in filtered["questions"])

    print("=" * 60)
    print(f"图谱: {graph_path}  sha256={graph_sha[:16]}…")
    print(f"  节点 {graph_payload['node_count']}  边 {graph_payload['edge_count']}")
    print(f"题库: {questions_path}  sha256={questions_sha[:16]}…")
    print(f"  题目 {bank_payload['count']}  类型 {dict(by_type)}")
    print(f"  难度 {dict(by_difficulty)}")
    print(f"目录: {catalog_path}  sha256={catalog_sha[:16]}…")
    print(f"  年级 {len(catalog_payload['grades'])} 个，知识点 {catalog_payload['topic_count']} 个")
    print("  年级分布: " + "  ".join(f"{pansgo.grade_label(g)}={by_grade[g]}" for g in sorted(by_grade)))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
