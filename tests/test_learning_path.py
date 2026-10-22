"""学习路径生成的单元测试。"""

import pytest

from src.learning_path import build_learning_path
from src.graph import build_digraph
from src.models import Edge, Node


def test_build_learning_path三级():
    g = build_digraph(
        [Node("A", "Concept", "本体"), Node("B", "Concept", "前置"), Node("C", "Concept", "巩固")],
        [Edge("B", "A", "prerequisites_for"), Edge("A", "C", "relates_to")],
    )
    path = build_learning_path(g, "A")
    assert path["body"] == "A"
    assert path["prerequisites"] == ["B"]
    assert path["consolidation"] == ["C"]


def test_前置链有环报错():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")],
        [Edge("A", "B", "prerequisites_for"), Edge("B", "A", "prerequisites_for")],
    )
    with pytest.raises(ValueError, match="环"):
        build_learning_path(g, "A")


def test_无前置时路径为空前置():
    g = build_digraph([Node("A", "Concept", "本体")], [])
    path = build_learning_path(g, "A")
    assert path["prerequisites"] == []
    assert path["consolidation"] == []
