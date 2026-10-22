"""API 接口测试：覆盖三组验收用例。"""

import pytest
from fastapi.testclient import TestClient

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


def test_ask_导数拒答():
    """验收用例 b：库外问题返回拒答 + 最接近知识点。"""
    resp = client.post("/api/ask", json={"question": "什么是导数"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is True
    assert "当前知识库未覆盖该内容" in data["answer"]
    assert data["knowledge_point"] is not None
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
