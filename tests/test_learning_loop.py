"""持续学习闭环：作答快照、错题聚合、标记、趋势计算。"""

import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import api, auth_deps, auth_service, db as db_module, pansgo, quiz_service
from src.schema import apply_migrations

QUESTIONS_PATH = Path("data/processed/pansgo_math_k12_questions.json")
QUESTION_PAYLOAD = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
ANSWERS = {q["id"]: str(q["answer"]) for q in QUESTION_PAYLOAD["questions"]}


@pytest.fixture
def loop_client(tmp_path):
    db_path = tmp_path / "loop.db"
    conn = db_module.connect(db_path)
    apply_migrations(conn)
    quiz_service.seed_questions(
        conn, QUESTION_PAYLOAD["questions"], pansgo.SOURCE_COMMIT
    )
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


def _register(db_path, username="learner"):
    conn = db_module.connect(db_path)
    try:
        result = auth_service.register_user(conn, username, "pass12345")
    finally:
        conn.close()
    return result["token"], result["user"]["id"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _start(client, token=None, **body):
    headers = _headers(token) if token else {}
    return client.post(
        "/api/diagnose/quiz", json={"action": "start", **body}, headers=headers
    )


def _answer(client, token, session_id, question, answer):
    headers = _headers(token) if token else {}
    return client.post(
        "/api/diagnose/quiz",
        json={
            "action": "answer",
            "session_id": session_id,
            "question_id": question["id"],
            "answer": answer,
        },
        headers=headers,
    )


def _answer_first_wrong(client, token, node_id="cnm_221"):
    started = _start(
        client,
        token,
        mode="single",
        node_ids=[node_id],
        max_questions=16,
        mastery_streak=3,
    ).json()
    question = started["question"]
    response = _answer(client, token, started["session_id"], question, "___wrong___")
    assert response.status_code == 200
    return started["session_id"], question


def _insert_session(
    conn,
    session_id,
    user_id,
    *,
    created_at,
    result,
    mode="single",
    grade=7,
    dataset_version=pansgo.SOURCE_COMMIT,
    scope_count=4,
):
    now = "2026-01-01T00:00:00.000Z"
    conn.execute(
        "INSERT INTO quiz_sessions "
        "(id, user_id, mode, grade, semester, scope_json, max_questions, "
        " mastery_streak, status, state_json, result_json, created_at, updated_at, "
        " finished_at, expires_at, dataset_version, scope_count) "
        "VALUES (?, ?, ?, ?, 'all', ?, 10, 3, 'completed', '{}', ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            user_id,
            mode,
            grade,
            json.dumps({"node_ids": ["a", "b", "c", "d"]}),
            json.dumps(result, ensure_ascii=False),
            created_at,
            created_at,
            created_at,
            "2099-01-01T00:00:00.000Z",
            dataset_version,
            scope_count,
        ),
    )
    conn.commit()


def _assessment(node_id, status, mastery_level=None):
    return {
        "id": node_id,
        "name": node_id.upper(),
        "grade": 7,
        "chapter": "七上 第一章",
        "chapter_label": "第一章",
        "status": status,
        "mastery_level": mastery_level or status,
        "max_correct_difficulty": None,
        "streak": 0,
        "asked": [],
        "wrong": [],
    }


def _result(assessments):
    counts = Counter(a["status"] for a in assessments)
    counts["proficient"] = sum(
        1 for a in assessments if a.get("mastery_level") == "proficient"
    )
    return {
        "mode": "single",
        "finished": True,
        "answered": 4,
        "max_questions": 10,
        "counts": {
            "mastered": counts.get("mastered", 0),
            "proficient": counts.get("proficient", 0),
            "unstable": counts.get("unstable", 0),
            "weak": counts.get("weak", 0),
            "untested": counts.get("untested", 0),
            "insufficient": counts.get("insufficient", 0),
        },
        "assessments": assessments,
        "weak": [a["id"] for a in assessments if a["status"] == "weak"],
        "root_causes": [],
        "learning_path": [],
        "chapters": [],
    }


def test_answer_writes_session_and_attempt_snapshots(loop_client):
    client, db_path = loop_client
    token, _ = _register(db_path)
    session_id, question = _answer_first_wrong(client, token, "cnm_221")

    conn = db_module.connect(db_path)
    try:
        attempt = conn.execute(
            "SELECT * FROM quiz_attempts WHERE session_id = ?", (session_id,)
        ).fetchone()
        session = conn.execute(
            "SELECT * FROM quiz_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    finally:
        conn.close()

    assert session["dataset_version"] == pansgo.SOURCE_COMMIT
    assert session["scope_count"] == 1
    assert attempt["dataset_version"] == pansgo.SOURCE_COMMIT
    assert attempt["difficulty"] == question["difficulty"]
    assert attempt["prompt_snapshot"] == question["prompt"]
    assert attempt["answer_snapshot"]
    assert attempt["choices_snapshot_json"] is not None
    assert attempt["topic_name"] == "配方法"
    assert attempt["chapter"]
    assert attempt["grade"] == 9


def test_wrong_questions_aggregate_by_question(loop_client):
    client, db_path = loop_client
    token, _ = _register(db_path)

    _, first_question = _answer_first_wrong(client, token)
    _, second_question = _answer_first_wrong(client, token)
    assert first_question["id"] == second_question["id"]

    response = client.get("/api/diagnose/wrong-questions", headers=_headers(token))
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["question_id"] == first_question["id"]
    assert item["wrong_count"] == 2
    assert item["prompt"] == first_question["prompt"]
    assert item["node_name"] == "配方法"
    assert item["student_answer"] == "___wrong___"
    assert item["correct_answer"]
    assert item["mark_status"] == "open"


def test_mark_wrong_question_filters_by_status(loop_client):
    client, db_path = loop_client
    token, _ = _register(db_path)
    _answer_first_wrong(client, token)

    items = client.get(
        "/api/diagnose/wrong-questions", headers=_headers(token)
    ).json()["items"]
    attempt_id = items[0]["attempt_id"]

    marked = client.post(
        f"/api/diagnose/wrong-questions/{attempt_id}/mark",
        json={"status": "mastered"},
        headers=_headers(token),
    )
    assert marked.status_code == 200
    assert marked.json()["status"] == "mastered"

    open_items = client.get(
        "/api/diagnose/wrong-questions?status=open", headers=_headers(token)
    ).json()
    assert open_items["total"] == 0

    mastered_items = client.get(
        "/api/diagnose/wrong-questions?status=mastered", headers=_headers(token)
    ).json()
    assert mastered_items["total"] == 1
    assert mastered_items["items"][0]["mark_status"] == "mastered"

    # 未登录不能标记
    assert client.post(
        f"/api/diagnose/wrong-questions/{attempt_id}/mark",
        json={"status": "ignored"},
    ).status_code == 401


def test_trends_compute_continuous_weak_improved_and_version_break(loop_client):
    client, db_path = loop_client
    token, user_id = _register(db_path)

    conn = db_module.connect(db_path)
    try:
        _insert_session(
            conn,
            "qs_s1",
            user_id,
            created_at="2026-01-01T09:00:00.000Z",
            result=_result([_assessment("a", "weak"), _assessment("b", "weak")]),
        )
        _insert_session(
            conn,
            "qs_s2",
            user_id,
            created_at="2026-01-02T09:00:00.000Z",
            result=_result([
                _assessment("a", "weak"),
                _assessment("b", "mastered"),
                _assessment("c", "weak"),
            ]),
        )
        # c 在版本变化后才变掌握：跨版本不能算作「已改善」
        _insert_session(
            conn,
            "qs_s3",
            user_id,
            created_at="2026-01-03T09:00:00.000Z",
            dataset_version="reseed-v2",
            result=_result([_assessment("a", "weak"), _assessment("c", "mastered")]),
        )
        _insert_session(
            conn,
            "qs_s4",
            user_id,
            created_at="2026-01-04T09:00:00.000Z",
            dataset_version="reseed-v2",
            result=_result([_assessment("a", "weak")]),
        )
        # 同一道题错两次
        for index, session_id in enumerate(("qs_s1", "qs_s2"), start=1):
            conn.execute(
                "INSERT INTO quiz_attempts "
                "(session_id, question_id, node_key, ordinal, student_answer, "
                " is_correct, created_at) VALUES (?, 'q_rep', 'a', ?, 'x', 0, ?)",
                (session_id, index, f"2026-01-0{index}T10:00:00.000Z"),
            )
        conn.commit()
    finally:
        conn.close()

    response = client.get("/api/diagnose/trends", headers=_headers(token))
    assert response.status_code == 200
    data = response.json()
    assert data["reason"] is None
    assert data["range"]["session_count"] == 4
    assert [s["session_id"] for s in data["sessions"]] == [
        "qs_s1",
        "qs_s2",
        "qs_s3",
        "qs_s4",
    ]
    # 覆盖率：已测 2 / 范围 4
    assert data["sessions"][0]["coverage"] == 0.5
    assert data["sessions"][0]["mastery_rate"] == 0.0
    assert data["sessions"][1]["mastery_rate"] == pytest.approx(1 / 3, abs=1e-4)

    assert data["version_breaks"] == [
        {"after_session": "qs_s2", "before_session": "qs_s3"}
    ]
    # 版本变化处断开：a 只统计新版本段内连续 2 次薄弱
    continuous = {item["node_key"]: item["count"] for item in data["continuous_weak"]}
    assert continuous == {"a": 2}
    improved = {item["node_key"]: item for item in data["improved"]}
    assert improved["b"]["from"] == "weak"
    assert improved["b"]["to"] == "mastered"
    # 跨版本变化不算「已改善」
    assert "c" not in improved
    repeated = {item["question_id"]: item["wrong_count"] for item in data["repeated_wrong"]}
    assert repeated == {"q_rep": 2}


def test_trends_need_at_least_two_sessions(loop_client):
    client, db_path = loop_client
    token, user_id = _register(db_path)
    conn = db_module.connect(db_path)
    try:
        _insert_session(
            conn,
            "qs_only",
            user_id,
            created_at="2026-01-01T09:00:00.000Z",
            result=_result([_assessment("a", "weak")]),
        )
    finally:
        conn.close()

    data = client.get("/api/diagnose/trends", headers=_headers(token)).json()
    assert data["reason"] == "not_enough_sessions"
    assert data["sessions"] == []
    assert data["range"]["session_count"] == 1
