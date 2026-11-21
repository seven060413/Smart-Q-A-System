"""命令行体验：用 pansgo 数学 K12 题库做一次学情诊断。

用法（项目根目录执行）：
    # 查知识点
    .venv/Scripts/python.exe scripts/diagnose_pansgo.py --search 配方法

    # 单点诊断
    .venv/Scripts/python.exe scripts/diagnose_pansgo.py --topic cnm_221

    # 整年级摸底（七年级，整学年，40 题）
    .venv/Scripts/python.exe scripts/diagnose_pansgo.py --grade 7 --max-questions 40 --mastery-streak 2

前置条件：已执行 scripts/fetch_pansgo.py 和 scripts/build_pansgo_graph.py。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph import build_digraph  # noqa: E402
from src.loader import load_edges, load_nodes  # noqa: E402
from src.question_bank import QuestionBank  # noqa: E402
from src.quiz_engine import QuizEngine  # noqa: E402

DEFAULT_GRAPH = ROOT / "data" / "processed" / "pansgo_math_k12.json"
DEFAULT_QUESTIONS = ROOT / "data" / "processed" / "pansgo_math_k12_questions.json"

STATUS_TEXT = {
    "mastered": "掌握",
    "unstable": "不稳",
    "weak": "薄弱",
    "untested": "未测",
    "insufficient": "题量不足",
}


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _topics_from(nodes):
    topics = {}
    for node in nodes:
        props = node.properties or {}
        topics[node.id] = {
            "id": node.id,
            "name": node.name,
            "grade": props.get("grade"),
            "semester": props.get("semester"),
            "book": props.get("book"),
            "chapter": props.get("chapter"),
            "chapter_label": props.get("chapter_label"),
        }
    return topics


def main() -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="pansgo 题库学情诊断（命令行）")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--topic", help="单点诊断：知识点 id，如 cnm_221")
    target.add_argument("--grade", type=int, help="整年级摸底：年级 1–14")
    target.add_argument("--node", action="append", help="章节诊断：可重复传入知识点 id")
    target.add_argument("--search", help="按名称模糊搜索知识点")
    parser.add_argument("--semester", default="all", help="整年级摸底：all / 上 / 下")
    parser.add_argument("--max-questions", type=int, default=None)
    parser.add_argument("--mastery-streak", type=int, default=None)
    parser.add_argument("--graph", default=str(DEFAULT_GRAPH))
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--json", action="store_true", help="结束后输出 JSON 结果")
    args = parser.parse_args()

    graph_path = Path(args.graph)
    questions_path = Path(args.questions)
    if not graph_path.exists() or not questions_path.exists():
        print("缺少数据文件，请先运行 scripts/fetch_pansgo.py 和 scripts/build_pansgo_graph.py", file=sys.stderr)
        return 1

    nodes = load_nodes(graph_path)
    topics = _topics_from(nodes)
    graph = build_digraph(nodes, load_edges(graph_path))
    bank = QuestionBank.from_path(questions_path)

    if args.search:
        keyword = args.search.strip()
        hits = [n for n in nodes if keyword in n.name or keyword in n.id]
        for node in hits[:30]:
            props = node.properties or {}
            print(f"{node.id}\t{node.name}\t{props.get('chapter_label') or props.get('chapter')}")
        print(f"共 {len(hits)} 条")
        return 0

    if args.topic:
        mode, node_ids = "single", [args.topic]
        default_max, default_streak = 16, 3
    elif args.node:
        mode, node_ids = "chapter", args.node
        default_max, default_streak = 16, 3
    elif args.grade:
        mode = "grade"
        node_ids = [
            t["id"]
            for t in topics.values()
            if t["grade"] == args.grade
            and (args.semester == "all" or t["semester"] == args.semester)
        ]
        default_max, default_streak = 40, 2
        if not node_ids:
            print(f"没有找到 {args.grade} 年级（{args.semester}）的知识点。", file=sys.stderr)
            return 1
    else:
        parser.error("需要 --topic / --node / --grade / --search 之一")

    unknown = [n for n in node_ids if n not in topics]
    if unknown:
        print(f"知识点不在图谱中: {unknown[:3]}", file=sys.stderr)
        return 1

    engine = QuizEngine.start(
        topics,
        graph,
        bank.by_topic,
        mode=mode,
        node_ids=node_ids,
        max_questions=args.max_questions or default_max,
        mastery_streak=args.mastery_streak or default_streak,
    )

    while not engine.state["finished"]:
        question = engine.current_question()
        if question is None:
            break
        print()
        print(f"[{question['node_name']}] {question['prompt']}")
        if question["choices"]:
            for choice in question["choices"]:
                print(f"  {choice.get('key')}. {choice.get('text')}")
        try:
            answer = input("作答（直接回车中止）: ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if not answer:
            break
        result = engine.answer(question["id"], answer)
        print("✓ 正确" if result["is_correct"] else "✗ 错误")
        if result.get("explanation"):
            print(f"  解析：{result['explanation']}")

    report = engine.result()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print()
    print("=" * 60)
    print(f"本次作答 {report['answered']} 题，状态统计: {report['counts']}")
    for item in report["assessments"]:
        print(f"  {STATUS_TEXT.get(item['status'], item['status']):<6} {item['name']}")
    if report["root_causes"]:
        names = [next((a["name"] for a in report["assessments"] if a["id"] == i), i) for i in report["root_causes"]]
        print("根因知识点: " + "、".join(names))
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
