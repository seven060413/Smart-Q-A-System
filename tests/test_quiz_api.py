"""学情诊断 API：目录、单点/整年级会话、幂等与错误路径。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import api, auth_deps, db as db_module, pansgo, quiz_service
from src.schema import apply_migrations

QUESTIONS_PATH = Path("data/processed/pansgo_math_k12_questions.json")
QUESTION_PAYLOAD = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
ANSWERS = {q["id"]: str(q["answer"]) for q in QUESTION_PAYLOAD["questions"]}


@pytest.fixture
def quiz_client(tmp_path):
    db_path = tmp_path / "quiz.db"
    conn = db_module.connect(db_path)
    apply_migrations(conn)
    quiz_service.seed_questions(conn, QUESTION_PAYLOAD["questions"], pansgo.SOURCE_COMMIT)
    conn.close()

    def override_get_db():
        c = db_module.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    api.app.dependency_overrides[auth_deps.get_db] = override_get_db
    with TestClient(api.app) as client:
        yield client, db_path
    api.app.dependency_overrides.clear()


def _start(client, **body):
    payload = {"action": "start", **body}
    return client.post("/api/diagnose/quiz", json=payload)


def _answer(client, session_id, question, answer, client_request_id=None):
    body = {
        "action": "answer",
        "session_id": session_id,
        "question_id": question["id"],
        "answer": answer,
    }
    if client_request_id:
        body["client_request_id"] = client_request_id
    return client.post("/api/diagnose/quiz", json=body)


def test_catalog_contains_primary_junior_and_high_school(quiz_client):
    client, _ = quiz_client
    resp = client.get("/api/diagnose/catalog")

    assert resp.status_code == 200
    data = resp.json()
    assert data["dataset"] == "pansgo_math_k12"
    assert data["topic_count"] == 870
    grades = {g["grade"]: g for g in data["grades"]}
    assert grades[1]["stage"] == "小学"
    assert grades[7]["stage"] == "初中"
    assert grades[10]["label"] == "高一"
    assert grades[14]["label"] == "选必三"
    assert all(t.get("chapter_label") for t in data["topics"])


@pytest.mark.parametrize("mode", ["single", "chapter"])
def test_session_records_derived_grade(quiz_client, mode):
    """单点/章节诊断也要落年级快照，供趋势/错题按年级筛选。"""
    client, db_path = quiz_client
    node_id = "cnm_p132"
    expected_grade = quiz_service.load_dataset().topics[node_id]["grade"]

    started = _start(client, mode=mode, node_ids=[node_id]).json()
    session_id = started["session_id"]

    conn = db_module.connect(db_path)
    try:
        row = conn.execute(
            "SELECT grade FROM quiz_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row["grade"] == expected_grade


def test_backfill_grade_snapshots_restores_old_session(quiz_client):
    client, db_path = quiz_client
    node_id = "cnm_p132"
    expected_grade = quiz_service.load_dataset().topics[node_id]["grade"]
    session_id = _start(client, mode="single", node_ids=[node_id]).json()["session_id"]

    conn = db_module.connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE quiz_sessions SET grade = NULL WHERE id = ?", (session_id,)
            )
        updated = quiz_service.backfill_grade_snapshots(conn)
        row = conn.execute(
            "SELECT grade FROM quiz_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()

    assert updated >= 1
    assert row["grade"] == expected_grade


def test_backfill_grade_snapshots_restores_attempt_without_dataset_version(quiz_client):
    client, db_path = quiz_client
    started = _start(client, mode="single", node_ids=["cnm_p132"]).json()
    question = started["question"]
    expected_grade = quiz_service.load_dataset().topics[question["node_key"]]["grade"]
    _answer(client, started["session_id"], question, ANSWERS[question["id"]])

    conn = db_module.connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE quiz_attempts SET grade = NULL, dataset_version = NULL "
                "WHERE session_id = ?",
                (started["session_id"],),
            )
        quiz_service.backfill_grade_snapshots(conn)
        row = conn.execute(
            "SELECT grade FROM quiz_attempts WHERE session_id = ?",
            (started["session_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert row["grade"] == expected_grade


def _has_answer_key(value) -> bool:
    if isinstance(value, dict):
        return "answer" in value or any(_has_answer_key(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_answer_key(v) for v in value)
    return False


def test_single_topic_mastery_flow_never_leaks_answer(quiz_client):
    client, _ = quiz_client
    started = _start(
        client, mode="single", node_ids=["cnm_p132"], max_questions=16, mastery_streak=3
    ).json()

    assert started["question"]["id"]
    assert not _has_answer_key(started["question"])
    session_id = started["session_id"]

    response = started
    for _ in range(3):
        question = response.get("question") or response.get("next_question")
        assert question is not None
        assert not _has_answer_key(question)
        response = _answer(client, session_id, question, ANSWERS[question["id"]]).json()
        assert not _has_answer_key(response)

    assert response["result"]["counts"]["mastered"] == 1
    assert response["result"]["finished"] is True


def test_wrong_twice_marks_weak_and_backtracks(quiz_client):
    client, _ = quiz_client
    started = _start(
        client, mode="single", node_ids=["cnm_221"], max_questions=16, mastery_streak=3
    ).json()
    session_id = started["session_id"]

    first = _answer(client, session_id, started["question"], "绝对不是答案").json()
    assert first["is_correct"] is False
    assert first["next_question"] is not None

    second = _answer(client, session_id, first["next_question"], "绝对不是答案").json()
    assert second["node_status"] == "weak"
    # 薄弱后应回溯到先修点
    assert second["next_question"] is not None
    assert second["next_question"]["node_key"] != "cnm_221"


def test_answer_is_idempotent_with_client_request_id(quiz_client):
    client, db_path = quiz_client
    started = _start(
        client, mode="single", node_ids=["cnm_p132"], max_questions=16, mastery_streak=3
    ).json()
    session_id = started["session_id"]
    question = started["question"]

    first = _answer(
        client, session_id, question, ANSWERS[question["id"]], client_request_id="req-1"
    )
    second = _answer(
        client, session_id, question, ANSWERS[question["id"]], client_request_id="req-1"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    conn = db_module.connect(db_path)
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE session_id = ?", (session_id,)
        ).fetchone()["c"]
    finally:
        conn.close()
    assert count == 1


def test_out_of_order_question_is_rejected(quiz_client):
    client, _ = quiz_client
    started = _start(
        client, mode="single", node_ids=["cnm_p132"], max_questions=16, mastery_streak=3
    ).json()

    resp = client.post(
        "/api/diagnose/quiz",
        json={
            "action": "answer",
            "session_id": started["session_id"],
            "question_id": "cnm_p132_q4",
            "answer": "1",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "QUIZ_STATE"


def test_grade_mode_and_abort(quiz_client):
    client, _ = quiz_client
    started = _start(
        client, mode="grade", grade=7, semester="all",
        max_questions=40, mastery_streak=2,
    ).json()

    assert started["question"]["grade"] == 7
    assert started["question"]["difficulty"] == "standard"

    aborted = client.post(
        "/api/diagnose/quiz",
        json={"action": "abort", "session_id": started["session_id"]},
    ).json()
    assert aborted["aborted"] is True

    again = client.post(
        "/api/diagnose/quiz",
        json={
            "action": "answer",
            "session_id": started["session_id"],
            "question_id": started["question"]["id"],
            "answer": ANSWERS[started["question"]["id"]],
        },
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "SESSION_FINISHED"


def test_invalid_scope_and_params(quiz_client):
    client, _ = quiz_client

    assert _start(client, mode="single", node_ids=[]).status_code == 400
    assert _start(client, mode="single", node_ids=["missing"]).status_code == 400
    assert _start(client, mode="single", node_ids=["cnm_p132", "cnm_p001"]).status_code == 400
    assert _start(
        client, mode="single", node_ids=["cnm_p132"], max_questions=2
    ).status_code == 400
    assert _start(
        client, mode="single", node_ids=["cnm_p132"], mastery_streak=4
    ).status_code == 400
    assert _start(client, mode="grade", grade=99).status_code == 422
