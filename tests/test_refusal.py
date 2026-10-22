"""拒答的单元测试。"""

from src.models import Node
from src.refusal import is_covered, link_top, refusal_message


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
