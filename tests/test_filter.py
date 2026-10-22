"""按年级 + importance 筛选知识点的单元测试。"""

from pathlib import Path

import pytest

from src.filter import (
    build_book_knowledge_points,
    filter_by_book,
    select_knowledge_points,
)
from src.loader import load_nodes
from src.models import Node

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "math.json"


def make_nodes():
    return [
        Node("math_5b_rjb_cpt1", "Concept", "分数", {"importance": "掌握"}),
        Node("math_5b_rjb_cpt2", "Concept", "通分", {"importance": "理解"}),
        Node("math_5b_rjb_skl1", "Skill", "画图", {}),
        Node("math_5b_rjb_ch1", "Chapter", "分数的意义和性质"),
        Node("math_6b_rjb_cpt1", "Concept", "比例", {"importance": "掌握"}),
    ]


def test_filter_by_book只保留指定册():
    got = filter_by_book(make_nodes(), "math_5b_rjb")
    assert {n.id for n in got} == {
        "math_5b_rjb_cpt1", "math_5b_rjb_cpt2",
        "math_5b_rjb_skl1", "math_5b_rjb_ch1",
    }


def test_select只取知识点并按importance降序():
    got = select_knowledge_points(filter_by_book(make_nodes(), "math_5b_rjb"))
    # Chapter 被排除，只保留 Concept + Skill
    assert {n.id for n in got} == {
        "math_5b_rjb_cpt1", "math_5b_rjb_cpt2", "math_5b_rjb_skl1",
    }
    # 掌握 > 理解 > 无 importance 的 Skill
    assert [n.id for n in got] == [
        "math_5b_rjb_cpt1", "math_5b_rjb_cpt2", "math_5b_rjb_skl1",
    ]


def test_重要层级不排在了解之后():
    nodes = [
        Node("c1", "Concept", "通分", {"importance": "重要"}),
        Node("c2", "Concept", "完全数", {"importance": "了解"}),
    ]
    got = select_knowledge_points(nodes)
    assert got[0].id == "c1"   # 「重要」是核心内容，不应排在「了解」后


def test_limit截断():
    got = select_knowledge_points(filter_by_book(make_nodes(), "math_5b_rjb"), limit=2)
    assert len(got) == 2
    assert got[0].id == "math_5b_rjb_cpt1"


@pytest.mark.skipif(not DATA_PATH.exists(), reason="未下载 math.json，跳过真实数据测试")
def test_真实数据五年级下册知识点数量与范围():
    kps = build_book_knowledge_points(load_nodes(DATA_PATH), "math_5b_rjb", limit=200)
    assert len(kps) == 59                # 45 Concept + 14 Skill
    assert len(kps) <= 200               # 满足规模约束
    for n in kps:
        assert n.id.startswith("math_5b_rjb_")
        assert n.label in {"Concept", "Skill"}
