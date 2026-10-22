"""实验 4 图谱构建：建图、前置传递闭包、环检测的单元测试。"""

from pathlib import Path

import networkx as nx
import pytest

from src.graph import (
    build_digraph,
    check_prereq_properties,
    find_cycles,
    indirect_prerequisites,
    load_5b_graph,
    prerequisite_graph,
    topological_order,
)
from src.models import Edge, Node

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed" / "math_5b_knowledge_graph.json"


def test_建图节点与边正确():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")],
        [Edge("A", "B", "prerequisites_for"), Edge("B", "A", "appears_in")],
    )
    assert set(g.nodes()) == {"A", "B"}
    assert g.number_of_edges() == 2
    assert g.nodes["A"]["name"] == "甲"


def test_多重关系边不被覆盖():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")],
        [Edge("A", "B", "prerequisites_for"), Edge("A", "B", "relates_to")],
    )
    assert g.number_of_edges() == 2          # 多关系图保留两条平行边
    pg = prerequisite_graph(g)
    assert pg.has_edge("A", "B")             # 前置边未被 relates_to 覆盖丢失
    assert pg.number_of_edges() == 1


def test_前置传递闭包():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"), Node("C", "Concept", "丙")],
        [Edge("A", "B", "prerequisites_for"), Edge("B", "C", "prerequisites_for")],
    )
    pg = prerequisite_graph(g)
    assert indirect_prerequisites(pg, "C") == {"A", "B"}   # A 是 C 的间接前置
    assert indirect_prerequisites(pg, "B") == {"A"}
    assert indirect_prerequisites(pg, "A") == set()


def test_环检测杀手用例():
    # 人为制造环：A 是 B 的前置，B 又是 A 的前置
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")],
        [Edge("A", "B", "prerequisites_for"), Edge("B", "A", "prerequisites_for")],
    )
    pg = prerequisite_graph(g)
    report = check_prereq_properties(pg)
    assert report["is_acyclic"] is False
    assert len(report["cycles"]) == 1
    cyc = report["cycles"][0]
    assert set(cyc) == {"A", "B"}     # 环覆盖 A、B
    assert cyc[0] == cyc[-1]          # 首尾相接，形成完整闭环序列
    # 无法生成学习路径
    with pytest.raises(nx.NetworkXUnfeasible):
        topological_order(pg)


def test_拓扑序前置在前():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"), Node("C", "Concept", "丙")],
        [Edge("A", "C", "prerequisites_for"), Edge("B", "C", "prerequisites_for")],
    )
    order = topological_order(prerequisite_graph(g))
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("C")


@pytest.mark.skipif(not PROCESSED.exists(), reason="子图尚未生成，跳过真实数据测试")
def test_真实数据前置图无环且传递闭包正确():
    g = load_5b_graph()
    pg = prerequisite_graph(g)
    report = check_prereq_properties(pg)
    assert report["is_acyclic"] is True
    assert report["edge_count"] == 20

    name2id = {d["name"]: n for n, d in pg.nodes(data=True)}
    # 真实传递链：3的倍数特征 → 倍数 → 偶数
    even = name2id["偶数"]
    assert indirect_prerequisites(pg, even) == {
        name2id["倍数"], name2id["3的倍数特征"],
    }
    # 该对节点同时有 relates_to，前置边不能被覆盖丢失
    assert pg.has_edge(
        name2id["最少称量次数"], name2id["物品数量与最少称量次数的关系"]
    )
