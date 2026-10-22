"""三组验收测试（期望结果先写，再运行）。

a. 异分母分数通分 → 本体 + 前置 + 人教版出处；
b. 「什么是导数」→ 拒答 + 最接近知识点；
c. 人为插入前置环 → 报环 + 输出完整节点序列。
"""

import pytest

from src.diagnosis import diagnose, format_citation
from src.graph import build_digraph, load_full_graph
from src.learning_path import build_learning_path
from src.linking import link_entity
from src.loader import load_nodes
from src.models import Edge, Node
from src.refusal import LINK_THRESHOLD, link_top, refusal_message
from src.subgraph import OUT_PATH


def test_a_异分母分数通分的诊断与溯源():
    """期望：本体=异分母分数加减法；必需前置含「通分方法」「同分母分数加减法」；
    建议前置含「分数的基本认识」；出处=人教版五年级下册·分数的加法和减法。

    注：操作手册示例的「最小公倍数/等值分数」在 K12-KGraph 真实数据中未直接连到本体
    （数据把「通分」概念与「通分方法」技能拆成两个节点且无边、无「等值分数」节点），
    故本测试以真实数据为准，差异在文档中说明。
    """
    nodes = load_nodes(OUT_PATH)          # 五年级下册知识点（链接候选）
    g = load_full_graph()                  # 全量图（含跨册前置）
    body = link_entity("为什么异分母分数相加要先通分", nodes, top_k=1)[0][0]
    assert body.name == "异分母分数加减法"

    result = diagnose(g, body.id)
    required = [g.nodes[i]["name"] for i in result["required"]]
    suggested = [g.nodes[i]["name"] for i in result["suggested"]]
    assert "通分方法" in required
    assert "同分母分数加减法" in required
    assert "分数的基本认识" in suggested

    citation = format_citation(g, body.id)
    assert "人教版五年级下册" in citation
    assert "分数的加法和减法" in citation


def test_b_什么是导数拒答():
    """期望：链接分数低于阈值 → 拒答「当前知识库未覆盖该内容」，并给出最接近知识点。"""
    nodes = load_nodes(OUT_PATH)
    node, score = link_top("什么是导数", nodes)
    assert score < LINK_THRESHOLD

    msg = refusal_message("什么是导数", nodes)
    assert msg["covered"] is False
    assert msg["message"] == "当前知识库未覆盖该内容"
    assert msg["closest"] is not None
    assert msg["closest_name"] is not None


def test_c_人为前置环报错并输出节点序列():
    """期望：插入 A↔B 前置环后，生成学习路径必须报错并输出完整闭环序列。"""
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")],
        [Edge("A", "B", "prerequisites_for"), Edge("B", "A", "prerequisites_for")],
    )
    with pytest.raises(ValueError) as exc:
        build_learning_path(g, "A")
    msg = str(exc.value)
    assert "环" in msg
    assert "A" in msg and "B" in msg
