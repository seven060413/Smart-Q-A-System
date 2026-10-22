"""实体链接的单元测试。"""

from pathlib import Path

import pytest

from src.linking import link_entity
from src.loader import load_nodes
from src.models import Node

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "math_5b_knowledge_graph.json"


def test_link_entity只链接知识点():
    nodes = [
        Node("c1", "Concept", "通分", {}),
        Node("ch1", "Chapter", "分数的意义"),
    ]
    hits = link_entity("什么是通分", nodes, top_k=3)
    assert all(n.label in ("Concept", "Skill") for n, _ in hits)


def test_link_entity合成用例():
    nodes = [
        Node("c1", "Concept", "异分母分数加减法", {}),
        Node("c2", "Concept", "通分", {}),
        Node("c3", "Concept", "最小公倍数", {}),
    ]
    hits = link_entity("为什么异分母分数相加要先通分", nodes, top_k=1)
    assert hits[0][0].id == "c1"


@pytest.mark.skipif(not DATA_PATH.exists(), reason="子图尚未生成，跳过真实数据测试")
def test_真实数据链接异分母分数通分():
    nodes = load_nodes(DATA_PATH)
    hits = link_entity("为什么异分母分数相加要先通分", nodes, top_k=3)
    assert hits[0][0].name == "异分母分数加减法"
