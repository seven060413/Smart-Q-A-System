"""问答范围/阈值配置的单元测试。"""

from src.refusal import LINK_THRESHOLD
from src.settings import qa_link_threshold, qa_match_scope


def test_qa_match_scope默认全量(monkeypatch):
    monkeypatch.delenv("QA_MATCH_SCOPE", raising=False)
    assert qa_match_scope() == "full"


def test_qa_match_scope可回滚(monkeypatch):
    monkeypatch.setenv("QA_MATCH_SCOPE", "book_5b")
    assert qa_match_scope() == "book_5b"


def test_qa_match_scope非法值回退(monkeypatch):
    monkeypatch.setenv("QA_MATCH_SCOPE", "unknown")
    assert qa_match_scope() == "full"


def test_qa_link_threshold(monkeypatch):
    monkeypatch.delenv("QA_LINK_THRESHOLD", raising=False)
    assert qa_link_threshold() == LINK_THRESHOLD

    monkeypatch.setenv("QA_LINK_THRESHOLD", "0.42")
    assert qa_link_threshold() == 0.42

    monkeypatch.setenv("QA_LINK_THRESHOLD", "not-a-number")
    assert qa_link_threshold() == LINK_THRESHOLD
