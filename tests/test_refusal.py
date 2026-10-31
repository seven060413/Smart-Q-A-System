"""拒答的单元测试。"""

from src.models import Node
from src.refusal import LINK_THRESHOLD, is_covered, link_top, refusal_message


def test_link_top与阈值():
    nodes = [
        Node("c1", "Concept", "异分母分数加减法", {}),
        Node("c2", "Concept", "倍数", {}),
    ]
    node, score = link_top("为什么异分母分数相加要先通分", nodes)
    assert node.id == "c1"
    assert is_covered("为什么异分母分数相加要先通分", nodes) is True
    assert is_covered("什么是导数", nodes) is False


def test_refusal_message():
    nodes = [Node("c1", "Concept", "倍数", {})]
    msg = refusal_message("什么是导数", nodes)
    assert msg == {
        "covered": False,
        "message": "当前知识库未覆盖该内容",
        "closest": "c1",
        "closest_name": "倍数",
    }


def test_单字知识点用明确问法兜底():
    """单字名不参与模糊打分，但「什么是 X」应精确命中。"""
    nodes = [Node("b", "Concept", "比", {})]
    node, score = link_top("什么是比", nodes)
    assert node.id == "b"
    assert score >= LINK_THRESHOLD
    assert is_covered("什么是比", nodes) is True

    # 普通句子里碰巧出现「比」不应命中
    assert is_covered("足球比赛规则是什么", nodes) is False


def test_精确命中优先更长名称():
    nodes = [
        Node("c1", "Concept", "分数", {}),
        Node("c2", "Concept", "真分数", {}),
    ]
    node, _ = link_top("什么是真分数", nodes)
    assert node.id == "c2"
