"""API 接口测试：覆盖三组验收用例。"""

import os

import pytest
from fastapi.testclient import TestClient

# 默认全量匹配；避免开发者本地 .env 设置 book_5b 影响测试预期。
os.environ["QA_MATCH_SCOPE"] = "full"

from src import api
from src.graph import build_digraph
from src.models import Edge, Node
from src.pipeline import run_qa

client = TestClient(api.app)


@pytest.fixture(autouse=True)
def mock_generator(monkeypatch):
    """测试不真实调用 Qwen，用固定回复替代。"""
    monkeypatch.setattr(api.generator, "generate", lambda prompt: "（测试讲解）")


def test_ask_异分母分数通分():
    """验收用例 a：库内问题返回完整结构化答案。"""
    resp = client.post("/api/ask", json={"question": "为什么异分母分数相加要先通分"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is False
    assert data["knowledge_point"] == "异分母分数加减法"
    assert data["source"].startswith("人教版五年级下册")
    assert data["answer"] == "（测试讲解）"
    assert any(g["name"] == "通分方法" for g in data["prerequisite_gaps"])
    assert data["learning_path"]["body"] == "异分母分数加减法"


def test_ask_导数已覆盖():
    """全量图谱模式下，高中「导数」也应被匹配，而不是拒答。"""
    resp = client.post("/api/ask", json={"question": "什么是导数"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is False
    assert data["knowledge_point"] == "导数"
    assert data["learning_path"]["body"] == "导数"


def test_ask_巩固练习独立返回(monkeypatch):
    """生成结果按【巩固练习】拆分：answer 只保留讲解，exercises 单独返回。"""
    monkeypatch.setattr(
        api.generator,
        "generate",
        lambda prompt: (
            "【讲解】\n1. 先补前置：先会分数单位。\n2. 再讲本体：真分数小于 1。\n\n"
            "【巩固练习】\n1. 题目：判断 3/5 是不是真分数。\n答案：是。\n"
            "2. 题目：写一个分母为 8 的真分数。\n答案：1/8。"
        ),
    )
    resp = client.post("/api/ask", json={"question": "什么是真分数"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is False
    assert "巩固练习" not in data["answer"]
    assert "真分数小于 1" in data["answer"]
    assert len(data["exercises"]) == 2
    assert data["exercises"][0].startswith("题目：判断")
    assert data["learning_path"]["exercises"] == data["exercises"]


def test_ask_库外问题拒答():
    """数学域外问题仍应拒答。"""
    resp = client.post("/api/ask", json={"question": "如何做红烧肉"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is True
    assert "当前知识库未覆盖该内容" in data["answer"]
    assert data["learning_path"] is None


def test_run_qa_环检测报错():
    """验收用例 c：人为插入前置环，流水线必须报错（禁止生成路径）。"""
    g = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")],
        [Edge("A", "B", "prerequisites_for"), Edge("B", "A", "prerequisites_for")],
    )
    kps = [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")]
    with pytest.raises(ValueError, match="环"):
        run_qa("什么是甲", g, kps)
