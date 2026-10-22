"""实验 1 集合建模：三个有限集合的单元测试。"""

from pathlib import Path

import pytest

from src.loader import load_nodes
from src.models import GraphSets, Node

# 真实数据文件路径（集成测试用）
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "math.json"


def make_small_graph() -> GraphSets:
    """构造一个 6 节点的合成小图谱，用于纯逻辑测试。"""
    return GraphSets([
        Node("book1", "Book", "一年级上册", {"subject": "数学", "publisher": "人教版"}),
        Node("ch1", "Chapter", "准备课"),
        Node("sec1", "Section", "数一数"),
        Node("cpt1", "Concept", "数物体（数一数）", {"definition": "逐一计数"}),
        Node("skl1", "Skill", "建立对应关系", {"description": "一一配对"}),
        Node("exe1", "Exercise", "看图比较多少", {"answer": "左边多"}),
    ])


def test_三个集合元素划分正确():
    g = make_small_graph()
    assert g.entity_set == {"book1", "ch1", "sec1", "cpt1", "skl1", "exe1"}
    assert g.knowledge_point_set == {"cpt1", "skl1"}   # Concept + Skill
    assert g.chapter_set == {"ch1", "sec1"}            # Chapter + Section


def test_知识点与章节互斥且都包含于实体集合():
    g = make_small_graph()
    E, K, C = g.entity_set, g.knowledge_point_set, g.chapter_set
    assert K & C == set()   # K ∩ C = ∅
    assert K <= E           # K ⊆ E
    assert C <= E           # C ⊆ E


def test_集合元素满足对应类型规则():
    g = make_small_graph()
    for nid in g.knowledge_point_set:
        assert g.node(nid).label in {"Concept", "Skill"}
    for nid in g.chapter_set:
        assert g.node(nid).label in {"Chapter", "Section"}


def test_重复id只算一个元素():
    g = GraphSets([Node("x", "Concept", "甲"), Node("x", "Concept", "甲")])
    assert g.entity_set == {"x"}
    assert len(g.entity_set) == 1


@pytest.mark.skipif(not DATA_PATH.exists(), reason="未下载 math.json，跳过真实数据测试")
def test_真实数据三个集合基数与关系():
    g = GraphSets(load_nodes(DATA_PATH))
    assert len(g.entity_set) == 2711
    assert len(g.knowledge_point_set) == 1898   # 1470 Concept + 428 Skill
    assert len(g.chapter_set) == 316            # 150 Chapter + 166 Section
    assert g.knowledge_point_set <= g.entity_set
    assert g.chapter_set <= g.entity_set
    assert g.knowledge_point_set & g.chapter_set == set()
