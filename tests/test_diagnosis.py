"""前置诊断（量词查询）的单元测试。"""

from src.diagnosis import dependents_of, diagnose, format_citation, prerequisites_of
from src.graph import build_digraph
from src.models import Edge, Node


def make_graph():
    return build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"), Node("C", "Concept", "丙")],
        [Edge("B", "A", "prerequisites_for"), Edge("C", "B", "prerequisites_for")],
    )


def test_prerequisites_of量词查询():
    g = make_graph()
    assert prerequisites_of(g, "A") == ["B", "C"]   # 含间接前置
    assert prerequisites_of(g, "B") == ["C"]


def test_dependents_of反向量词查询():
    g = make_graph()
    assert dependents_of(g, "C") == ["A", "B"]      # 以 C 为前置（含间接）


def test_diagnose必需与建议():
    g = make_graph()
    result = diagnose(g, "A")
    assert result["body"] == "A"
    assert result["required"] == ["B"]     # 直接前置 = 必需
    assert result["suggested"] == ["C"]    # 间接前置 = 建议


def test_format_citation():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("ch1", "Chapter", "分数的加法和减法")],
        [Edge("A", "ch1", "appears_in")],
    )
    assert format_citation(g, "A") == "人教版五年级下册·分数的加法和减法"
