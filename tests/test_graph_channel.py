"""图谱通道（相邻子图/连通性/路径）的单元测试。"""

from src.graph import (
    build_digraph,
    has_path,
    neighbor_subgraph,
    shortest_path,
    weakly_connected_components,
)
from src.models import Edge, Node


def test_neighbor_subgraph():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"),
         Node("C", "Concept", "丙"), Node("D", "Concept", "丁")],
        [Edge("A", "B", "prerequisites_for"), Edge("A", "C", "relates_to"),
         Edge("C", "D", "is_a")],
    )
    assert set(neighbor_subgraph(g, {"A"}, radius=1).nodes()) == {"A", "B", "C"}
    assert set(neighbor_subgraph(g, {"A"}, radius=2).nodes()) == {"A", "B", "C", "D"}


def test_has_path与最短路径():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"), Node("C", "Concept", "丙")],
        [Edge("A", "B", "prerequisites_for"), Edge("B", "C", "prerequisites_for")],
    )
    assert has_path(g, "A", "C") is True
    assert has_path(g, "C", "A") is False
    assert shortest_path(g, "A", "C") == ["A", "B", "C"]
    assert shortest_path(g, "C", "A") == []


def test_weakly_connected_components():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"), Node("C", "Concept", "丙")],
        [Edge("A", "B", "relates_to")],
    )
    comps = weakly_connected_components(g)
    assert len(comps) == 2   # {A,B} 与 {C}
