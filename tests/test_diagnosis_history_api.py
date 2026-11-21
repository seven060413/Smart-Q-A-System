"""诊断历史读接口：认证、所有者、分页、旧数据兼容与图谱。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import api, auth_deps, auth_service, db as db_module, pansgo, quiz_service
from src.schema import apply_migrations

QUESTIONS_PATH = Path("data/processed/pansgo_math_k12_questions.json")
QUESTION_PAYLOAD = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
ANSWERS = {q["id"]: str(q["answer"]) for q in QUESTION_PAYLOAD["questions"]}


@pytest.fixture
def history_client(tmp_path):
    db_path = tmp_path / "history.db"
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


def _register(db_path, username):
    conn = db_module.connect(db_path)
    try:
        result = auth_service.register_user(conn, username, "pass12345")
    finally:
        conn.close()
    return result["token"], result["user"]["id"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _start(client, token, **body):
    return client.post(
        "/api/diagnose/quiz",
        json={"action": "start", **body},
        headers=_headers(token),
    )


def _answer(client, token, session_id, question, answer):
    return client.post(
        "/api/diagnose/quiz",
        json={
            "action": "answer",
            "session_id": session_id,
            "question_id": question["id"],
            "answer": answer,
        },
        headers=_headers(token),
    )


def _complete_single(client, token, node_id="cnm_p132"):
    started = _start(
        client,
        token,
        mode="single",
        node_ids=[node_id],
        max_questions=16,
        mastery_streak=3,
    ).json()
    session_id = started["session_id"]
    question = started["question"]
    response = None
    for _ in range(40):
        if question is None:
            break
        response = _answer(
            client, token, session_id, question, ANSWERS[question["id"]]
        ).json()
        if response.get("result"):
            break
        question = response.get("next_question")
    return session_id, response


def _insert_session(
    conn,
    session_id,
    user_id,
    *,
    created_at,
    result_json,
    dataset_version=None,
    scope_count=None,
    status="completed",
    mode="single",
    grade=7,
):
    conn.execute(
        "INSERT INTO quiz_sessions "
        "(id, user_id, mode, grade, semester, scope_json, max_questions, "
        " mastery_streak, status, state_json, result_json, created_at, updated_at, "
        " finished_at, expires_at, dataset_version, scope_count) "
        "VALUES (?, ?, ?, ?, 'all', ?, 10, 3, ?, '{}', ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            user_id,
            mode,
            grade,
            json.dumps({"node_ids": ["cnm_221", "cnm_148"]}),
            status,
            result_json,
            created_at,
            created_at,
            created_at if status == "completed" else None,
            "2099-01-01T00:00:00.000Z",
            dataset_version,
            scope_count,
        ),
    )
    conn.commit()


def _legacy_result():
    """旧版 result_json：没有 mastery_level / max_correct_difficulty。"""
    return json.dumps(
        {
            "mode": "single",
            "finished": True,
            "answered": 2,
            "max_questions": 16,
            "counts": {"mastered": 0, "unstable": 0, "weak": 1, "untested": 0, "insufficient": 0},
            "assessments": [
                {
                    "id": "cnm_221",
                    "name": "配方法",
                    "grade": 9,
                    "chapter": "九上 第二十五章 一元二次方程 25.2",
                    "chapter_label": "第二十五章 一元二次方程 25.2",
                    "status": "weak",
                    "streak": 0,
                    "asked": ["cnm_221_q1", "cnm_221_q2"],
                    "wrong": ["cnm_221_q1", "cnm_221_q2"],
                }
            ],
            "weak": ["cnm_221"],
            "root_causes": [],
            "learning_path": [],
            "chapters": [],
        },
        ensure_ascii=False,
    )


def test_history_endpoints_require_login(history_client):
    client, _ = history_client
    assert client.get("/api/diagnose/sessions").status_code == 401
    assert client.get("/api/diagnose/wrong-questions").status_code == 401
    assert client.get("/api/diagnose/trends").status_code == 401


def test_latest_is_204_when_no_completed_session(history_client):
    client, db_path = history_client
    token, _ = _register(db_path, "latest_user")
    response = client.get("/api/diagnose/sessions/latest", headers=_headers(token))
    assert response.status_code == 204

    # 游客不保存历史
    assert client.get("/api/diagnose/sessions/latest").status_code == 404


def test_guest_session_is_readable_without_login(history_client):
    client, db_path = history_client
    started = client.post(
        "/api/diagnose/quiz",
        json={
            "action": "start",
            "mode": "single",
            "node_ids": ["cnm_221"],
            "max_questions": 16,
            "mastery_streak": 3,
        },
    ).json()

    response = client.get(f"/api/diagnose/sessions/{started['session_id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == started["session_id"]
    assert data["status"] == "active"
    # 未完成会话返回当前题目，便于前端「继续」
    assert data["question"]["id"] == started["question"]["id"]
    assert data["question"].get("answer") is None


def test_session_owner_check_returns_404(history_client):
    client, db_path = history_client
    token_a, _ = _register(db_path, "owner_a")
    token_b, _ = _register(db_path, "owner_b")
    session_id, _ = _complete_single(client, token_a)

    # 非所有者按 404 处理，避免泄露会话是否存在
    assert (
        client.get(
            f"/api/diagnose/sessions/{session_id}", headers=_headers(token_b)
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/diagnose/sessions/{session_id}", headers=_headers(token_a)
        ).status_code
        == 200
    )


def test_single_result_contains_counts_and_all_assessments(history_client):
    client, db_path = history_client
    token, _ = _register(db_path, "result_user")
    session_id, _ = _complete_single(client, token)

    data = client.get(
        f"/api/diagnose/sessions/{session_id}", headers=_headers(token)
    ).json()
    assert data["status"] == "completed"
    assert data["counts"]["mastered"] == 1
    assert data["counts"]["proficient"] in (0, 1)
    assert len(data["assessments"]) == 1
    assessment = data["assessments"][0]
    assert assessment["asked_count"] == len(assessment["asked"])
    assert assessment["wrong_count"] == len(assessment["wrong"])
    assert assessment["mastery_level"] in ("mastered", "proficient")
    assert assessment["max_correct_difficulty"] in (
        "basic",
        "standard",
        "challenge",
        "advanced",
    )
    assert data["scope_count"] == 1
    assert data["answered"] == 3


def test_legacy_result_fields_are_backfilled(history_client):
    client, db_path = history_client
    token, user_id = _register(db_path, "legacy_user")
    conn = db_module.connect(db_path)
    try:
        _insert_session(
            conn,
            "qs_legacy",
            user_id,
            created_at="2026-02-01T09:00:00.000Z",
            result_json=_legacy_result(),
        )
    finally:
        conn.close()

    data = client.get(
        "/api/diagnose/sessions/qs_legacy", headers=_headers(token)
    ).json()
    assessment = data["assessments"][0]
    assert assessment["mastery_level"] == "weak"
    assert assessment["max_correct_difficulty"] is None
    assert assessment["asked_count"] == 2
    assert assessment["wrong_count"] == 2
    assert data["counts"]["proficient"] == 0
    # 旧会话没有 dataset_version，回退当前数据集版本
    assert data["dataset_version"] == pansgo.SOURCE_COMMIT
    # 旧会话没有 scope_count，从 scope_json 推断
    assert data["scope_count"] == 2


def test_session_history_pagination(history_client):
    client, db_path = history_client
    token, user_id = _register(db_path, "page_user")
    conn = db_module.connect(db_path)
    try:
        for index in range(3):
            _insert_session(
                conn,
                f"qs_page{index}",
                user_id,
                created_at=f"2026-03-0{index + 1}T09:00:00.000Z",
                result_json=_legacy_result(),
                dataset_version=pansgo.SOURCE_COMMIT,
                scope_count=2,
            )
    finally:
        conn.close()

    first = client.get(
        "/api/diagnose/sessions?limit=2", headers=_headers(token)
    ).json()
    assert len(first["items"]) == 2
    assert [i["session_id"] for i in first["items"]] == ["qs_page2", "qs_page1"]
    assert first["next_cursor"]

    second = client.get(
        f"/api/diagnose/sessions?limit=2&cursor={first['next_cursor']}",
        headers=_headers(token),
    ).json()
    assert [i["session_id"] for i in second["items"]] == ["qs_page0"]
    assert second["next_cursor"] is None

    item = first["items"][0]
    assert item["status"] == "completed"
    assert item["counts"]["weak"] == 1
    assert item["coverage"] == 0.5
    assert item["mastery_rate"] == 0.0


def test_wrong_question_filters(history_client):
    client, db_path = history_client
    token, _ = _register(db_path, "filter_user")
    started = _start(
        client,
        token,
        mode="single",
        node_ids=["cnm_221"],
        max_questions=16,
        mastery_streak=3,
    ).json()
    question = started["question"]
    _answer(client, token, started["session_id"], question, "___wrong___")

    all_items = client.get(
        "/api/diagnose/wrong-questions", headers=_headers(token)
    ).json()
    assert all_items["total"] == 1
    assert all_items["summary"]["total"] == 1
    assert all_items["summary"]["node_count"] == 1
    assert all_items["summary"]["oldest_at"]
    assert all_items["mark_counts"] == {"open": 1, "mastered": 0, "ignored": 0}
    assert all_items["nodes"][0]["node_key"] == "cnm_221"
    assert all_items["nodes"][0]["wrong_count"] == 1
    assert [g["grade"] for g in all_items["grades"]] == [9]
    assert all_items["chapters"] and all_items["chapters"][0]["count"] == 1

    assert (
        client.get(
            "/api/diagnose/wrong-questions?node_key=cnm_221", headers=_headers(token)
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            "/api/diagnose/wrong-questions?node_key=cnm_148", headers=_headers(token)
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            "/api/diagnose/wrong-questions?grade=9", headers=_headers(token)
        ).json()["total"]
        == 1
    )
    assert (
        client.get(
            "/api/diagnose/wrong-questions?grade=7", headers=_headers(token)
        ).json()["total"]
        == 0
    )
    assert (
        client.get(
            "/api/diagnose/wrong-questions?days=7", headers=_headers(token)
        ).json()["total"]
        == 1
    )
    # 非法状态返回 400
    assert (
        client.get(
            "/api/diagnose/wrong-questions?status=bad", headers=_headers(token)
        ).status_code
        == 400
    )


def test_graph_from_node_keys_and_session(history_client):
    client, db_path = history_client
    token, user_id = _register(db_path, "graph_user")

    # 显式种子：先修链 + hard/soft 边
    data = client.get(
        "/api/diagnose/graph?node_keys=cnm_221&depth=2"
    ).json()
    node_ids = {node["id"] for node in data["nodes"]}
    assert "cnm_221" in node_ids
    assert data["seeds"] == ["cnm_221"]
    assert {edge["strength"] for edge in data["edges"]} <= {"hard", "soft"}
    assert all(node["status"] is None for node in data["nodes"])
    edge_pairs = {(e["source"], e["target"]) for e in data["edges"]}
    assert ("cnm_148", "cnm_221") in edge_pairs

    # 会话种子：薄弱点与状态颜色
    conn = db_module.connect(db_path)
    try:
        _insert_session(
            conn,
            "qs_graph",
            user_id,
            created_at="2026-04-01T09:00:00.000Z",
            result_json=_legacy_result(),
        )
    finally:
        conn.close()

    session_graph = client.get(
        "/api/diagnose/graph?session_id=qs_graph&depth=1", headers=_headers(token)
    ).json()
    assert "cnm_221" in session_graph["seeds"]
    by_id = {node["id"]: node for node in session_graph["nodes"]}
    assert by_id["cnm_221"]["status"] == "weak"
    assert by_id["cnm_221"]["mastery_level"] == "weak"

    # 非所有者不能借会话读取图谱
    token_b, _ = _register(db_path, "graph_other")
    assert (
        client.get(
            "/api/diagnose/graph?session_id=qs_graph", headers=_headers(token_b)
        ).status_code
        == 404
    )

    # 未知种子
    assert client.get("/api/diagnose/graph?node_keys=missing").status_code == 400
    assert client.get("/api/diagnose/graph").status_code == 400
