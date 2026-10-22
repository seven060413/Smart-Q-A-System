"""文本通道的单元测试。"""

import numpy as np
from pathlib import Path

import pytest

from src.models import Node
from src.retrieval import TextRetriever, cosine_topk, knowledge_point_text


def test_knowledge_point_text():
    c = Node("c1", "Concept", "通分", {"definition": "化成同分母"})
    s = Node("s1", "Skill", "画图", {"description": "用图形表示"})
    assert knowledge_point_text(c) == "通分：化成同分母"
    assert knowledge_point_text(s) == "画图：用图形表示"


def test_cosine_topk():
    ids = ["a", "b", "c"]
    matrix = np.array([[1, 0], [0, 1], [1, 1]], dtype=float)
    query = np.array([1, 0], dtype=float)
    hits = cosine_topk(query, matrix, ids, k=2)
    assert hits[0][0] == "a"              # 与 [1,0] 完全相同
    assert abs(hits[0][1] - 1.0) < 1e-6
    assert hits[1][0] == "c"              # [1,1] 比 [0,1] 更接近


class DictEmbedder:
    """测试用：相同文本得相同向量。"""
    def __init__(self, dim=8):
        self._dim = dim
        self._cache = {}

    def encode(self, texts):
        import zlib
        out = []
        for t in texts:
            if t not in self._cache:
                rng = np.random.default_rng(zlib.crc32(t.encode("utf-8")))
                self._cache[t] = rng.standard_normal(self._dim)
            out.append(self._cache[t])
        return np.array(out)


def test_text_retriever召回():
    nodes = [
        Node("c1", "Concept", "分数", {"definition": "把单位1平均分成若干份"}),
        Node("c2", "Concept", "通分", {"definition": "化成同分母"}),
        Node("c3", "Skill", "画图", {"description": "用图形表示"}),
    ]
    retriever = TextRetriever(nodes, DictEmbedder())
    # 查询文本恰好等于 c2 的向量化文本 → c2 应排第一、余弦≈1.0
    hits = retriever.retrieve(knowledge_point_text(nodes[1]), k=3)
    assert hits[0][0] == "c2"
    assert abs(hits[0][1] - 1.0) < 1e-6


INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"


@pytest.mark.skipif(not (INDEX_DIR / "kp_vectors.npy").exists(), reason="未构建 bge-m3 向量索引")
def test_真实bge_m3召回异分母分数():
    from src.retrieval import BgeM3Embedder, cosine_topk, load_index

    matrix, ids = load_index(INDEX_DIR)
    emb = BgeM3Embedder()
    qv = emb.encode(["为什么异分母分数相加要先通分"])[0]
    hits = cosine_topk(qv, matrix, ids, k=5)
    # 目标知识点 math_5b_rjb_cpt35（异分母分数加减法）应进入 Top-K
    assert "math_5b_rjb_cpt35" in [i for i, _ in hits]
