"""题库加载与本地判题。

题库格式见 `data/processed/pansgo_math_k12_questions.json`，兼容两种写法：
- 顶层是题目数组；
- 顶层是对象，题目在 ``questions`` 键下。

判题规则覆盖 pansgo 的四种题型：numeric / choice / short / self。
- numeric：支持整数、小数、分数（``3/4``）、百分数（``50%``）与多答案；
- choice：接受选项字母（``A``/``a``/``Ａ``）或正确选项的完整文字；
- short：忽略空白与全半角后比对，另支持 ``accept`` 等价答案；
- self：开放题，无法自动判分，返回 ``None``。

本模块只做本地比对，不执行题库里的 ``verify`` 表达式。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DIFFICULTY_ORDER = {"basic": 0, "standard": 1, "challenge": 2, "advanced": 2}
_ANSWER_SPLIT = re.compile(r"[,，;；]")


@dataclass(frozen=True)
class Question:
    id: str
    topic_id: str
    difficulty: str
    type: str
    prompt: str
    answer: Any
    choices: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    explanation: str = ""
    verify: str = ""
    figure: str = ""
    accept: Tuple[str, ...] = field(default_factory=tuple)
    unordered: bool = False
    hide_choice_text: bool = False

    @property
    def gradable(self) -> bool:
        """开放题（self）无法自动判分。"""
        return self.type != "self"

    @property
    def is_diagnostic(self) -> bool:
        """pansgo 约定 _q1 是知识点的诊断题（与 diagnostic_question 对齐）。"""
        return self.id.endswith("_q1")


class QuestionBank:
    """按知识点组织的题库。"""

    def __init__(self, questions: Iterable[Question]):
        self._by_id: Dict[str, Question] = {}
        self._by_topic: Dict[str, List[Question]] = {}
        for q in questions:
            self._by_id[q.id] = q
            self._by_topic.setdefault(q.topic_id, []).append(q)
        for topic_id, items in self._by_topic.items():
            items.sort(key=lambda q: (0 if q.is_diagnostic else 1,
                                      DIFFICULTY_ORDER.get(q.difficulty, 9), q.id))

    @classmethod
    def from_path(cls, path: Path | str) -> "QuestionBank":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("questions", []) if isinstance(data, dict) else data
        return cls(question_from_dict(item) for item in raw)

    def get(self, question_id: str) -> Optional[Question]:
        return self._by_id.get(question_id)

    def by_topic(self, topic_id: str) -> List[Question]:
        return list(self._by_topic.get(topic_id, ()))

    def pick(self, topic_id: str, limit: int = 2, exclude: Iterable[str] = ()) -> List[Question]:
        """按诊断题优先、由易到难取题。"""
        skip = set(exclude)
        picked = [q for q in self._by_topic.get(topic_id, ()) if q.id not in skip]
        return picked[:limit]

    @property
    def topic_ids(self) -> List[str]:
        return sorted(self._by_topic)

    def __len__(self) -> int:
        return len(self._by_id)


def question_from_dict(item: Dict[str, Any]) -> Question:
    return Question(
        id=str(item.get("id", "")),
        topic_id=str(item.get("topicId") or item.get("topic_id") or ""),
        difficulty=str(item.get("difficulty") or ""),
        type=str(item.get("type") or "choice"),
        prompt=str(item.get("prompt") or ""),
        answer=item.get("answer"),
        choices=tuple(item.get("choices") or ()),
        explanation=str(item.get("explanation") or ""),
        verify=str(item.get("verify") or ""),
        figure=str(item.get("figure") or ""),
        accept=tuple(str(a) for a in (item.get("accept") or ())),
        unordered=bool(item.get("unordered")),
        hide_choice_text=bool(
            item.get("hideChoiceText") or item.get("hide_choice_text")
        ),
    )


def grade_answer(question: Question, response: Any) -> Optional[bool]:
    """判分。返回 True/False；开放题返回 None。"""
    if not question.gradable:
        return None
    if response is None:
        return False
    if question.type == "choice":
        return _grade_choice(question, str(response))
    if question.type == "numeric":
        return _grade_numeric(question, str(response))
    return _grade_text(question, str(response))


def _grade_choice(question: Question, response: str) -> bool:
    resp = _norm(response)
    correct = _norm(str(question.answer))
    for choice in question.choices:
        key = _norm(str(choice.get("key") or ""))
        text = _norm(str(choice.get("text") or ""))
        # answer 可能是字母，也可能是选项文字；字母不区分大小写。
        is_correct = _ci_equal(key, correct) or _ci_equal(text, correct)
        is_response = _ci_equal(resp, key) or _ci_equal(resp, text)
        if is_correct and is_response:
            return True
    return False


def _ci_equal(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()


def _grade_numeric(question: Question, response: str) -> bool:
    expected = _split_answers(str(question.answer))
    given = _split_answers(response)
    if not given:
        return False
    # pansgo 用全角「，」分隔多答案，默认按顺序比较；unordered=true 时顺序无关。
    if question.unordered:
        expected, given = sorted(expected), sorted(given)
    if len(expected) != len(given):
        return False
    return all(_same_value(a, b) for a, b in zip(expected, given))


def _grade_text(question: Question, response: str) -> bool:
    candidates = [question.answer, *question.accept]
    resp = _norm(str(response))
    return any(resp == _norm(str(c)) for c in candidates if c is not None)


def _split_answers(text: str) -> List[str]:
    return [p.strip() for p in _ANSWER_SPLIT.split(text.strip()) if p.strip()]


def _same_value(a: str, b: str) -> bool:
    fa, fb = _to_fraction(a), _to_fraction(b)
    if fa is not None and fb is not None:
        return fa == fb
    return _norm(a) == _norm(b)


def _to_fraction(text: str) -> Optional[Fraction]:
    s = _norm(text).replace(" ", "")
    if not s:
        return None
    percent = s.endswith("%")
    if percent:
        s = s[:-1]
    try:
        value = Fraction(s)
    except (ValueError, ZeroDivisionError):
        try:
            value = Fraction(str(float(s)))
        except (ValueError, OverflowError):
            return None
    return value / 100 if percent else value


def _norm(text: str) -> str:
    """全半角统一、去首尾空白、连续空白压成一个。"""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()
