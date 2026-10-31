"""评估问答匹配范围扩展后的链接阈值、候选规模与前置诊断规模。

用法（项目根目录）：
    .venv/Scripts/python.exe scripts/evaluate_qa_scope.py
    .venv/Scripts/python.exe scripts/evaluate_qa_scope.py --scope book_5b

只做离线统计，不调用大模型、不写数据库。
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

import networkx as nx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph import load_full_graph, prerequisite_graph
from src.linking import link_entity
from src.loader import load_nodes
from src.refusal import LINK_THRESHOLD, link_top
from src.subgraph import OUT_PATH, RAW_PATH

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


NEGATIVE_QUESTIONS = [
    "如何做红烧肉", "今天天气怎么样", "苹果手机怎么截图", "李白是哪位诗人",
    "英语单词apple怎么读", "怎么用Photoshop抠图", "如何申请护照", "明天会下雨吗",
    "如何写一首古诗", "红烧排骨的做法", "怎样练好普通话发音", "电脑蓝屏怎么解决",
    "如何提高写作水平", "中国首都是哪里", "怎么养多肉植物", "如何学习吉他",
    "足球比赛规则是什么", "怎么做蛋炒饭", "如何制作PPT", "秦始皇统一六国的时间",
    "如何拍人像照片", "微信怎么改头像", "如何种植西红柿", "钢琴有多少个琴键",
    "怎样快速入睡", "如何做蛋糕", "猫咪不吃东西怎么办", "怎样挑选西瓜",
    "电影票怎么退", "如何练习书法", "衣服上的油渍怎么洗", "世界最高的山是哪座",
    "如何更换汽车轮胎", "怎样学习英语语法", "如何煮咖啡", "手机电池不耐用怎么办",
    "如何训练小狗", "为什么天空是蓝色的", "如何做俯卧撑", "怎样写简历",
    "如何选择大学专业", "股票怎么开户", "如何办理签证", "怎样保养皮肤",
    "如何修理自行车", "如何做沙拉", "怎样提高记忆力", "如何学习游泳",
    "火车票怎么改签", "如何种植玫瑰",
]

NATURAL_POSITIVE_QUESTIONS = [
    "为什么异分母分数相加要先通分",
    "怎么把两个分母不同的分数加起来",
    "圆面积怎么算",
    "三角形内角和是多少",
    "怎样求一个数的百分之几",
    "一元二次方程怎么解",
    "函数图像怎么画",
    "概率怎么计算",
    "什么是倍数",
    "什么是分数",
    "什么是导数",
    "什么是通分",
]


def _quantile(values: list[int], q: float) -> int:
    if not values:
        return 0
    return sorted(values)[min(len(values) - 1, int(q * len(values)))]


def _prereq_stats(graph: nx.MultiDiGraph, kp_nodes) -> None:
    pg = prerequisite_graph(graph)
    direct, indirect, consolidation = [], [], []
    for node in kp_nodes:
        nid = node.id
        direct.append(len(list(pg.predecessors(nid))) if nid in pg else 0)
        indirect.append(len(nx.ancestors(pg, nid)) if nid in pg else 0)
        descendants = set(nx.descendants(pg, nid)) if nid in pg else set()
        relates = {
            e[1]
            for e in graph.out_edges(nid, data=True)
            if e[-1].get("type") == "relates_to"
        } if nid in graph else set()
        consolidation.append(len(descendants | relates))

    print("前置/巩固规模：")
    for name, values in [
        ("直接前置", direct),
        ("全部前置(含间接)", indirect),
        ("巩固层", consolidation),
    ]:
        print(
            f"  {name}: median={statistics.median(values):.1f} "
            f"p90={_quantile(values, 0.9)} p99={_quantile(values, 0.99)} "
            f"max={max(values)}"
        )
    print(f"  前置图是否 DAG: {nx.is_directed_acyclic_graph(pg)}")


def _threshold_table(nodes, threshold: float) -> None:
    print(f"\n当前阈值 LINK_THRESHOLD={threshold:.2f}")
    neg_scores = []
    for q in NEGATIVE_QUESTIONS:
        hits = link_entity(q, nodes, top_k=1)
        neg_scores.append(hits[0][1] if hits else 0.0)
    print(f"域外问题（{len(NEGATIVE_QUESTIONS)} 条）最高模糊分: {max(neg_scores):.3f}")

    print("\n阈值  | 域外被误接受 | 自然数学问题被接受")
    print("------+--------------+------------------")
    for t in [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]:
        neg_accept = sum(1 for q in NEGATIVE_QUESTIONS if link_top(q, nodes, t)[1] >= t)
        pos_accept = sum(
            1 for q in NATURAL_POSITIVE_QUESTIONS if link_top(q, nodes, t)[1] >= t
        )
        print(
            f"{t:.2f}  | {neg_accept:>12}/{len(NEGATIVE_QUESTIONS)} "
            f"| {pos_accept:>15}/{len(NATURAL_POSITIVE_QUESTIONS)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=["full", "book_5b"], default="full")
    args = parser.parse_args()

    graph = load_full_graph()
    path = OUT_PATH if args.scope == "book_5b" else RAW_PATH
    nodes = load_nodes(path)
    kps = [n for n in nodes if n.label in ("Concept", "Skill")]

    print(f"范围: {args.scope}  文件: {path}")
    print(f"节点: {len(nodes)}  知识点(Concept/Skill): {len(kps)}")
    name_counts = Counter(n.name for n in kps)
    dup = {name: c for name, c in name_counts.items() if c > 1}
    print(f"重名知识点: {len(dup)} 个，最大重复 {max(name_counts.values())}")

    _prereq_stats(graph, kps)
    _threshold_table(nodes, LINK_THRESHOLD)

    # 全量名称问句的正确率与低分情况
    total, correct, low = 0, 0, 0
    for node in kps:
        hits = link_entity(f"什么是{node.name}", nodes, top_k=1)
        if not hits:
            continue
        total += 1
        matched, score = hits[0]
        if matched.id == node.id or matched.name == node.name:
            correct += 1
        if score < 0.2:
            low += 1
    if total:
        print(
            f"\n「什么是{{知识点名}}」Top-1 同名/同 id: {correct}/{total} "
            f"({correct / total:.1%})；模糊分 <0.2 的 {low} 条（单字名，由精确问法兜底）"
        )


if __name__ == "__main__":
    main()
