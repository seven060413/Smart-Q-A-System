"""学情诊断引擎：掌握 / 不稳 / 薄弱 / 未测 / 题量不足。"""

import networkx as nx

from src.question_bank import question_from_dict
from src.quiz_engine import (
    STATUS_INSUFFICIENT,
    STATUS_MASTERED,
    STATUS_UNSTABLE,
    STATUS_UNTESTED,
    STATUS_WEAK,
    QuizEngine,
    QuizStateError,
)


def _topic(tid, name=None, grade=7, chapter="七上 第一章 有理数 1.1"):
    return {
        "id": tid,
        "name": name or tid,
        "grade": grade,
        "chapter": chapter,
        "chapter_label": chapter.split(" ", 1)[-1],
    }


def _q(tid, n, difficulty, answer="1"):
    return question_from_dict(
        {
            "id": f"{tid}_q{n}",
            "topicId": tid,
            "difficulty": difficulty,
            "type": "numeric",
            "prompt": f"{tid} 第 {n} 题",
            "answer": answer,
        }
    )


def _four(tid):
    return [
        _q(tid, 1, "basic"),
        _q(tid, 2, "basic"),
        _q(tid, 3, "standard"),
        _q(tid, 4, "challenge"),
    ]


def _engine(nodes, questions, edges=(), *, mode="single", ids=None, max_q=16, n=3):
    topics = {t["id"]: t for t in nodes}
    g = nx.DiGraph()
    g.add_nodes_from(topics)
    g.add_edges_from(edges)
    questions_for = lambda tid: questions.get(tid, [])  # noqa: E731
    return QuizEngine.start(
        topics,
        g,
        questions_for,
        mode=mode,
        node_ids=ids or list(topics),
        max_questions=max_q,
        mastery_streak=n,
    )


def _answer_current(engine, response="1"):
    question = engine.current_question()
    assert question is not None
    return engine.answer(question["id"], response)


def test_clean_run_masters():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"])

    assert engine.current_question()["difficulty"] == "basic"
    first = _answer_current(engine)
    assert first["is_correct"] is True
    assert first["next_question"]["difficulty"] == "standard"
    second = _answer_current(engine)
    assert second["next_question"]["difficulty"] == "challenge"
    third = _answer_current(engine)

    assert third["next_question"] is None
    assert third["result"]["counts"]["mastered"] == 1
    assert third["result"]["assessments"][0]["status"] == STATUS_MASTERED
    assert engine.state["finished"] is True


def test_wrong_then_confirmation_correct_is_unstable():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"])

    first = engine.answer("c_q1", "错")
    assert first["is_correct"] is False
    assert first["next_question"]["difficulty"] == "basic"  # 降级确认

    second = _answer_current(engine)
    assert second["result"]["assessments"][0]["status"] == STATUS_UNSTABLE
    assert second["result"]["counts"]["unstable"] == 1
    assert engine.state["finished"] is True


def test_wrong_twice_is_weak_and_backtracks():
    nodes = [_topic("c"), _topic("a")]
    engine = _engine(nodes, {"c": _four("c"), "a": _four("a")}, edges=[("a", "c")], ids=["c"])

    engine.answer("c_q1", "错")
    response = _answer_current(engine, "错")

    # c 判薄弱后回溯到 a，并继续问 a 的题
    assert response["result"] is None
    assert response["next_question"]["node_key"] == "a"

    _answer_current(engine)
    _answer_current(engine)
    final = _answer_current(engine)

    result = final["result"]
    assert result["counts"]["weak"] == 1
    assert result["counts"]["mastered"] == 1
    assert result["weak"] == ["c"]
    assert result["root_causes"] == ["c"]       # a 已掌握，根因就在 c
    assert result["learning_path"] == ["c"]


def test_one_question_is_insufficient():
    engine = _engine([_topic("c")], {"c": [_q("c", 1, "basic")]}, ids=["c"])

    assert engine.current_question() is None
    result = engine.result()
    assert result["assessments"][0]["status"] == STATUS_INSUFFICIENT
    assert result["counts"]["insufficient"] == 1


def test_cap_marks_untested():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"], max_q=2, n=3)

    _answer_current(engine)
    response = _answer_current(engine)

    assert response["progress"]["finished"] is True
    assert response["result"]["assessments"][0]["status"] == STATUS_UNTESTED
    assert response["result"]["counts"]["untested"] == 1


def test_mastery_streak_5_uses_available_questions():
    # 只有 4 题时，N=5 按 4 题判定
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"], n=5)

    for _ in range(3):
        response = _answer_current(engine)
    response = _answer_current(engine)

    assert response["result"]["assessments"][0]["status"] == STATUS_MASTERED
    assert response["result"]["assessments"][0]["effective_mastery"] == 4


def test_mastered_with_challenge_is_proficient():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"], n=3)

    _answer_current(engine)
    _answer_current(engine)
    response = _answer_current(engine)

    assessment = response["result"]["assessments"][0]
    assert assessment["status"] == STATUS_MASTERED
    assert assessment["max_correct_difficulty"] == "challenge"
    assert assessment["mastery_level"] == "proficient"
    # mastered 仍包含熟练，proficient 是子集
    assert response["result"]["counts"]["mastered"] == 1
    assert response["result"]["counts"]["proficient"] == 1


def test_mastered_without_challenge_is_mastered():
    questions = {
        "c": [
            _q("c", 1, "basic"),
            _q("c", 2, "basic"),
            _q("c", 3, "standard"),
        ]
    }
    engine = _engine([_topic("c")], questions, ids=["c"], n=3)

    _answer_current(engine)
    _answer_current(engine)
    response = _answer_current(engine)

    assessment = response["result"]["assessments"][0]
    assert assessment["status"] == STATUS_MASTERED
    assert assessment["max_correct_difficulty"] == "standard"
    assert assessment["mastery_level"] == "mastered"
    assert response["result"]["counts"]["proficient"] == 0


def test_history_is_recorded_per_answer():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"])
    first = engine.current_question()
    engine.answer(first["id"], "1")

    history = engine.state["nodes"]["c"]["history"]
    assert history == [
        {"question_id": first["id"], "difficulty": first["difficulty"], "correct": True}
    ]


def test_old_state_without_history_falls_back():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"])
    for node_state in engine.state["nodes"].values():
        node_state.pop("history", None)

    result = engine.result()
    assessment = result["assessments"][0]
    assert assessment["mastery_level"] == assessment["status"]
    assert assessment["max_correct_difficulty"] is None
    assert result["counts"]["proficient"] == 0


def test_grade_mode_starts_with_standard():
    engine = _engine(
        [_topic("c")], {"c": _four("c")}, mode="grade", ids=["c"]
    )
    assert engine.current_question()["difficulty"] == "standard"


def test_round_robin_by_chapter():
    nodes = [
        _topic("a1", chapter="七上 第一章 有理数"),
        _topic("a2", chapter="七上 第一章 有理数"),
        _topic("b1", chapter="七上 第二章 整式"),
        _topic("b2", chapter="七上 第二章 整式"),
    ]
    questions = {n["id"]: _four(n["id"]) for n in nodes}
    engine = _engine(nodes, questions, ids=[n["id"] for n in nodes])

    assert engine.state["queue"] == ["a1", "b1", "a2", "b2"]


def test_public_question_has_no_answer():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"])
    question = engine.current_question()
    assert "answer" not in question
    assert "verify" not in question
    assert question["prompt"].startswith("c 第")


def test_answer_out_of_order_is_rejected():
    engine = _engine([_topic("c")], {"c": _four("c")}, ids=["c"])
    try:
        engine.answer("c_q2", "1")
    except QuizStateError:
        pass
    else:
        raise AssertionError("应当拒绝乱序题号")
