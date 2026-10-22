"""五年级下册子图抽取的单元测试。"""

import json
from collections import Counter
from pathlib import Path

import pytest

from src.filter import build_book_knowledge_points
from src.loader import load_edges, load_nodes
from src.models import Edge, Node
from src.subgraph import build_math_5b_subgraph, extract_subgraph

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "math.json"


def make_graph():
    nodes = [
        Node("math_5b_rjb_cpt1", "Concept", "通分"),
        Node("math_5b_rjb_cpt2", "Concept", "分数"),
        Node("math_5b_rjb_ch1", "Chapter", "分数的意义"),
        Node("math_4b_rjb_cpt9", "Concept", "因数"),
        Node("math_6a_rjb_ch7", "Chapter", "跨册章"),
    ]
    edges = [
        Edge("math_5b_rjb_cpt2", "math_5b_rjb_cpt1", "prerequisites_for"),   # 保留：两端在种子
        Edge("math_4b_rjb_cpt9", "math_5b_rjb_cpt1", "prerequisites_for"),   # 排除：跨册
        Edge("math_5b_rjb_cpt1", "math_5b_rjb_ch1", "appears_in"),           # 保留：本册章
        Edge("math_5b_rjb_cpt1", "math_6a_rjb_ch7", "appears_in"),           # 排除：跨册章
    ]
    return nodes, edges


def test_extract_subgraph只保留种子内边与本册章节():
    nodes, edges = make_graph()
    sub_nodes, sub_edges = extract_subgraph(
        nodes, edges, {"math_5b_rjb_cpt1", "math_5b_rjb_cpt2"}, "math_5b_rjb"
    )
    assert {n.id for n in sub_nodes} == {
        "math_5b_rjb_cpt1", "math_5b_rjb_cpt2", "math_5b_rjb_ch1",
    }
    assert [(e.source, e.target, e.type) for e in sub_edges] == [
        ("math_5b_rjb_cpt1", "math_5b_rjb_ch1", "appears_in"),
        ("math_5b_rjb_cpt2", "math_5b_rjb_cpt1", "prerequisites_for"),
    ]


@pytest.mark.skipif(not DATA_PATH.exists(), reason="未下载 math.json，跳过真实数据测试")
def test_真实数据子图规模与完整性():
    nodes = load_nodes(DATA_PATH)
    edges = load_edges(DATA_PATH)
    seed = {n.id for n in build_book_knowledge_points(nodes, "math_5b_rjb")}
    sub_nodes, sub_edges = extract_subgraph(nodes, edges, seed, "math_5b_rjb")

    node_ids = {n.id for n in sub_nodes}
    assert len(sub_nodes) == 67
    assert len(sub_edges) == 92
    assert all(n.id.startswith("math_5b_rjb_") for n in sub_nodes)
    assert Counter(e.type for e in sub_edges) == {
        "appears_in": 65, "prerequisites_for": 20, "relates_to": 6, "is_a": 1,
    }
    # 无悬空端点
    for e in sub_edges:
        assert e.source in node_ids
        assert e.target in node_ids


@pytest.mark.skipif(not DATA_PATH.exists(), reason="未下载 math.json，跳过真实数据测试")
def test_真实数据appears_in只指向本册章节():
    nodes = load_nodes(DATA_PATH)
    edges = load_edges(DATA_PATH)
    seed = {n.id for n in build_book_knowledge_points(nodes, "math_5b_rjb")}
    sub_nodes, sub_edges = extract_subgraph(nodes, edges, seed, "math_5b_rjb")
    label = {n.id: n.label for n in sub_nodes}
    for e in sub_edges:
        if e.type == "appears_in":
            assert label[e.target] == "Chapter"


@pytest.mark.skipif(not DATA_PATH.exists(), reason="未下载 math.json，跳过真实数据测试")
def test_build写出可解析的JSON(tmp_path):
    out = tmp_path / "sub.json"
    sub_nodes, sub_edges = build_math_5b_subgraph(DATA_PATH, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["book_id"] == "math_5b_rjb"
    assert data["node_count"] == len(sub_nodes) == 67
    assert data["edge_count"] == len(sub_edges) == 92
