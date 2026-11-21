"""个性化推荐：错题、聊天、年级软权重与首页今日建议。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import api, auth_deps, db as db_module, pansgo, quiz_service, rate_limit
from src.schema import apply_migrations
from src.security import now_utc

QUESTIONS_PATH = Path("data/processed/pansgo_math_k12_questions.json")
QUESTION_PAYLOAD = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))

GRADE5_NODE = "cnm_p132"  # 五年级，已有题目
GRADE9_NODE = "cnm_221"  # 九年级，已有题目


@pytest.fixture
def recommend_client(tmp_path, monkeypatch):
    db_path = tmp_path / "recommend.db"
    conn = db_module.connect(db_path)
    apply_migrations(conn)
    quiz_service.seed_questions(
        conn, QUESTION_PAYLOAD["questions"], pansgo.SOURCE_COMMIT
    )
    now = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO courses (id, code, name, subject, status, created_at, updated_at) "
            "VALUES ('math', 'math', '小学数学', 'math', 'active', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO graph_versions "
            "(id, course_id, scope, book_id, active_slot, dataset_name, source_path, "
            " source_sha256, imported_at, is_active) "
            "VALUES ('math:subject_full', 'math', 'subject_full', NULL, 'subject_full', "
            "        'test', 'data/raw/math.json', 'x', ?, 1)",
            (now,),
        )
        conn.execute(
            "INSERT INTO graph_versions "
            "(id, course_id, scope, book_id, active_slot, dataset_name, source_path, "
            " source_sha256, imported_at, is_active) "
            "VALUES ('math:book:math_5b_rjb', 'math', 'book', 'math_5b_rjb', "
            "        'book:math_5b_rjb', 'test', 'data/processed/math_5b.json', 'y', ?, 1)",
            (now,),
        )
    conn.close()

    def override_get_db():
        c = db_module.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    api.app.dependency_overrides[auth_deps.get_db] = override_get_db
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("AUTH_SCRYPT_N", "1024")
    monkeypatch.setattr(api.generator, "generate", lambda prompt: "（测试讲解）")
    rate_limit.reset()

    with TestClient(api.app) as client:
        yield client, db_path

    rate_limit.reset()
    api.app.dependency_overrides.clear()


def _register(client, username="rec_stu"):
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Password123"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["token"], data["user"]["id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _set_grade(client, token, grade):
    resp = client.put(
        "/api/auth/profile", json={"grade": grade}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text


def _wrong_once(client, token, node_id):
    started = client.post(
        "/api/diagnose/quiz",
        json={"action": "start", "mode": "single", "node_ids": [node_id]},
        headers=_auth(token),
    )
    assert started.status_code == 200, started.text
    data = started.json()
    answered = client.post(
        "/api/diagnose/quiz",
        json={
            "action": "answer",
            "session_id": data["session_id"],
            "question_id": data["question"]["id"],
            "answer": "definitely wrong",
        },
        headers=_auth(token),
    )
    assert answered.status_code == 200, answered.text
    return data["session_id"]


def _today(client, token, limit=3):
    resp = client.get(
        f"/api/recommendations/today?limit={limit}", headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_today_requires_login(recommend_client):
    client, _ = recommend_client
    assert client.get("/api/recommendations/today").status_code == 401


def test_wrong_question_drives_today(recommend_client):
    client, _ = recommend_client
    token, _ = _register(client)
    _set_grade(client, token, 5)
    _wrong_once(client, token, GRADE5_NODE)

    data = _today(client, token)
    items = data["items"]
    assert items
    top = items[0]
    assert top["node_key"] == GRADE5_NODE
    assert top["kind"] in ("wrong", "trend")
    assert "错" in top["reason"]
    assert top["actions"][0]["type"] == "diagnose"
    assert data["reason"] is None


def test_chat_topic_drives_today(recommend_client):
    client, _ = recommend_client
    token, _ = _register(client)
    _set_grade(client, token, 5)

    asked = client.post(
        "/api/ask", json={"question": "什么是真分数"}, headers=_auth(token)
    )
    assert asked.status_code == 200, asked.text

    items = _today(client, token, limit=5)["items"]
    chat_items = [item for item in items if item["kind"] == "chat"]
    assert chat_items
    assert any("真分数" in item["name"] for item in chat_items)


def test_unmapped_chat_node_only_offers_chat(recommend_client):
    """聊天图谱节点无法映射到诊断图谱时，不能给「去诊断」这种会跳空的入口。"""
    client, db_path = recommend_client
    token, user_id = _register(client)
    now = now_utc()
    conn = db_module.connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO conversations "
                "(id, user_id, course_id, title, created_at, updated_at, last_message_at) "
                "VALUES ('conv_fake', ?, 'math', '测试', ?, ?, ?)",
                (user_id, now, now, now),
            )
            conn.execute(
                "INSERT INTO messages "
                "(id, conversation_id, user_id, role, content, status, refused, "
                " created_at, updated_at) "
                "VALUES ('msg_fake', 'conv_fake', ?, 'assistant', 'x', 'completed', 0, ?, ?)",
                (user_id, now, now),
            )
            conn.execute(
                "INSERT INTO message_knowledge_points "
                "(message_id, graph_version_id, node_key, node_name, relation, ordinal) "
                "VALUES ('msg_fake', 'math:subject_full', 'math_9a_fake', "
                "        '不存在的知识点', 'body', 0)"
            )
    finally:
        conn.close()

    items = _today(client, token, limit=3)["items"]
    item = next(i for i in items if i["node_key"] == "math_9a_fake")
    assert item["kind"] == "chat"
    assert item["grade"] == 9
    assert [action["type"] for action in item["actions"]] == ["chat"]


def test_grade_is_soft_prior_not_a_filter(recommend_client):
    """九年级内容不会被隐藏，但同分的五年级内容应排在前面。"""
    client, _ = recommend_client
    token, _ = _register(client)
    _set_grade(client, token, 5)
    _wrong_once(client, token, GRADE5_NODE)
    _wrong_once(client, token, GRADE9_NODE)

    items = _today(client, token, limit=10)["items"]
    by_key = {item["node_key"]: item for item in items}
    assert GRADE5_NODE in by_key
    assert GRADE9_NODE in by_key
    assert by_key[GRADE5_NODE]["score"] > by_key[GRADE9_NODE]["score"]


def test_prerequisite_of_weak_node_is_suggested(recommend_client):
    client, _ = recommend_client
    token, _ = _register(client)
    _set_grade(client, token, 5)
    _wrong_once(client, token, GRADE5_NODE)

    items = _today(client, token, limit=10)["items"]
    prereq_items = [item for item in items if item["kind"] == "prerequisite"]
    assert prereq_items
    assert any("前置" in item["reason"] for item in prereq_items)


def test_mastered_wrong_is_excluded(recommend_client):
    client, db_path = recommend_client
    token, user_id = _register(client)
    _set_grade(client, token, 5)
    session_id = _wrong_once(client, token, GRADE5_NODE)

    conn = db_module.connect(db_path)
    try:
        attempt = conn.execute(
            "SELECT question_id, dataset_version FROM quiz_attempts "
            "WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        with conn:
            conn.execute(
                "INSERT INTO wrong_question_marks "
                "(user_id, dataset_version, question_id, node_key, status, updated_at) "
                "VALUES (?, ?, ?, ?, 'mastered', ?)",
                (
                    user_id,
                    attempt["dataset_version"],
                    attempt["question_id"],
                    GRADE5_NODE,
                    now_utc(),
                ),
            )
    finally:
        conn.close()

    items = _today(client, token)["items"]
    assert all(item["node_key"] != GRADE5_NODE for item in items)


def test_new_user_gets_onboarding(recommend_client):
    client, _ = recommend_client
    token, _ = _register(client)
    _set_grade(client, token, 4)

    data = _today(client, token)
    assert data["items"]
    item = data["items"][0]
    assert item["kind"] == "onboarding"
    assert item["actions"][0]["type"] == "diagnose"
    assert data["reason"] == "no_data"
