"""题库加载与判题。"""

import json

from src.question_bank import QuestionBank, grade_answer, question_from_dict


def _q(**kw):
    base = {
        "id": "t1_q1",
        "topicId": "t1",
        "difficulty": "basic",
        "type": "numeric",
        "prompt": "题干",
        "answer": "3",
    }
    base.update(kw)
    return question_from_dict(base)


def test_numeric_accepts_fraction_decimal_and_fullwidth():
    q = _q(answer="3/4")
    assert grade_answer(q, "0.75") is True
    assert grade_answer(q, "３／４") is True
    assert grade_answer(q, "4/3") is False


def test_numeric_multiple_answers_respect_unordered():
    ordered = _q(answer="2，-2")
    assert grade_answer(ordered, "2，-2") is True
    assert grade_answer(ordered, "-2，2") is False

    unordered = _q(answer="2，-2", unordered=True)
    assert grade_answer(unordered, "-2，2") is True


def test_numeric_percent_and_bad_input():
    q = _q(answer="50%")
    assert grade_answer(q, "0.5") is True
    assert grade_answer(q, "50") is False
    assert grade_answer(q, "") is False
    assert grade_answer(q, "不是数") is False


def test_choice_accepts_key_or_text():
    q = _q(
        type="choice",
        answer="A",
        choices=[{"key": "A", "text": "不一定能"}, {"key": "B", "text": "一定能"}],
    )
    assert grade_answer(q, "A") is True
    assert grade_answer(q, "a") is True
    assert grade_answer(q, "Ａ") is True
    assert grade_answer(q, "不一定能") is True
    assert grade_answer(q, "B") is False


def test_short_and_self():
    q = _q(type="short", answer="通分", accept=["先通分"])
    assert grade_answer(q, " 通分 ") is True
    assert grade_answer(q, "先通分") is True
    assert grade_answer(q, "约分") is False

    open_q = _q(type="self", answer="参考")
    assert grade_answer(open_q, "随便") is None


def test_bank_pick_puts_diagnostic_first(tmp_path):
    payload = {
        "questions": [
            {"id": "t1_q3", "topicId": "t1", "difficulty": "standard", "type": "numeric",
             "prompt": "p3", "answer": "3"},
            {"id": "t1_q1", "topicId": "t1", "difficulty": "basic", "type": "numeric",
             "prompt": "p1", "answer": "1"},
            {"id": "t1_q2", "topicId": "t1", "difficulty": "challenge", "type": "numeric",
             "prompt": "p2", "answer": "2"},
        ]
    }
    path = tmp_path / "q.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    bank = QuestionBank.from_path(path)
    assert len(bank) == 3
    picked = bank.pick("t1", limit=2)
    assert [q.id for q in picked] == ["t1_q1", "t1_q3"]
    assert bank.get("t1_q2").difficulty == "challenge"
    assert bank.by_topic("missing") == []
