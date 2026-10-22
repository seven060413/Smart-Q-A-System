"""双通道检索融合的单元测试。"""

from src.fusion import dual_retrieve, fuse, graph_channel_hits
from src.graph import build_digraph
from src.models import Edge, Node


def test_fuse加权求和():
    text = {"A": 0.9, "B": 0.2}
    graph = {"B": 1.0}
    ranked = fuse(text, graph, alpha=0.7)
    scores = dict(ranked)
    assert abs(scores["A"] - 0.63) < 1e-9
    assert abs(scores["B"] - 0.44) < 1e-9
    assert ranked[0][0] == "A"


def test_graph_channel_hits():
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"),
         Node("C", "Concept", "丙"), Node("D", "Concept", "丁"),
         Node("ch1", "Chapter", "章")],
        [Edge("B", "A", "prerequisites_for"), Edge("A", "C", "relates_to"),
         Edge("A", "ch1", "appears_in")],
    )
    hits = graph_channel_hits(g, "A")
    assert hits == {"B": 1.0, "C": 1.0}   # 前置 B、邻居 C；章节 ch1 被过滤、D 无关


class FakeTextRetriever:
    def retrieve(self, query, k=3):
        return [("B", 0.5), ("A", 0.9)]


def test_dual_retrieve编排():
    nodes = [Node("A", "Concept", "甲"), Node("B", "Concept", "乙"), Node("C", "Concept", "丙")]
    g = build_digraph(
        nodes,
        [Edge("B", "A", "prerequisites_for"), Edge("A", "C", "relates_to")],
    )
    result = dual_retrieve("甲", nodes, g, FakeTextRetriever(), top_k=3)
    assert result["anchor"] == "A"
    assert "B" in result["prerequisites"]
    # 融合后前置 B 被图通道抬升，超过文本分更高的 A
    assert result["ranked"][0][0] == "B"
