"""阶段 5：聊天会话与消息持久化、越权、分页、失败记录测试。"""

import json

import pytest
from fastapi.testclient import TestClient

from src import api, auth_deps, db as db_module, rate_limit
from src.schema import apply_migrations
from src.security import now_utc

QUESTION = "为什么异分母分数相加要先通分"


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    db_path = tmp_path / "chat.db"
    conn = db_module.connect(db_path)
    apply_migrations(conn)
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


def _register(client, username="stu_a"):
    resp = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Password123"},
    )
    assert resp.status_code == 201
    return resp.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _ask(client, token=None, question=QUESTION, **extra):
    headers = _auth(token) if token else {}
    body = {"question": question}
    body.update(extra)
    return client.post("/api/ask", json=body, headers=headers)


def _rows(db_path, sql, params=()):
    conn = db_module.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_guest_ask_is_not_persisted(chat_client):
    client, db_path = chat_client
    resp = _ask(client)
    assert resp.status_code == 200
    data = resp.json()
    assert data["persisted"] is False
    assert data["answer"] == "（测试讲解）"
    assert "prompt" not in data and "_meta" not in data

    assert _rows(db_path, "SELECT COUNT(*) AS c FROM conversations")[0]["c"] == 0
    assert _rows(db_path, "SELECT COUNT(*) AS c FROM messages")[0]["c"] == 0


def test_guest_cannot_use_conversation_id(chat_client):
    client, db_path = chat_client
    resp = _ask(client, conversation_id="whatever")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_REQUIRED"
    assert _rows(db_path, "SELECT COUNT(*) AS c FROM messages")[0]["c"] == 0


def test_invalid_token_is_not_treated_as_guest(chat_client):
    client, db_path = chat_client
    resp = client.post(
        "/api/ask",
        json={"question": QUESTION},
        headers=_auth("not-a-real-token"),
    )
    assert resp.status_code == 401
    assert _rows(db_path, "SELECT COUNT(*) AS c FROM messages")[0]["c"] == 0


def test_auth_ask_creates_conversation_and_saves_metadata(chat_client):
    client, db_path = chat_client
    token = _register(client)

    resp = _ask(client, token)
    assert resp.status_code == 200
    data = resp.json()
    assert data["persisted"] is True
    assert data["conversation_id"]
    assert data["user_message_id"] and data["assistant_message_id"]
    assert data["knowledge_point"] == "异分母分数加减法"
    assert data["answer"] == "（测试讲解）"

    conv = _rows(
        db_path,
        "SELECT * FROM conversations WHERE id = ?",
        (data["conversation_id"],),
    )[0]
    assert conv["user_id"] == _rows(
        db_path, "SELECT id FROM users WHERE username = 'stu_a'"
    )[0]["id"]
    assert conv["title"] == QUESTION

    msgs = _rows(
        db_path,
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY rowid",
        (data["conversation_id"],),
    )
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assistant = msgs[1]
    assert assistant["content"] == "（测试讲解）"
    assert assistant["status"] == "completed"
    assert assistant["refused"] == 0
    assert assistant["graph_version_id"] == "math:book:math_5b_rjb"
    assert assistant["context_graph_version_id"] == "math:subject_full"
    assert assistant["reply_to_message_id"] == msgs[0]["id"]
    assert json.loads(assistant["learning_path_json"])["body"] == "异分母分数加减法"
    assert any(
        g["name"] == "通分方法"
        for g in json.loads(assistant["prerequisite_gaps_json"])
    )

    kps = _rows(
        db_path,
        "SELECT relation, node_key, node_name, graph_version_id "
        "FROM message_knowledge_points WHERE message_id = ?",
        (assistant["id"],),
    )
    relations = {r["relation"] for r in kps}
    assert "body" in relations
    assert "prerequisite_required" in relations
    assert all(r["node_key"] for r in kps)


def test_auth_ask_appends_to_existing_conversation(chat_client):
    client, _ = chat_client
    token = _register(client)

    created = client.post(
        "/api/conversations",
        json={"title": "我的会话"},
        headers=_auth(token),
    )
    assert created.status_code == 201
    cid = created.json()["id"]

    resp = _ask(client, token, conversation_id=cid)
    assert resp.status_code == 200
    assert resp.json()["conversation_id"] == cid

    detail = client.get(f"/api/conversations/{cid}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["title"] == "我的会话"
    assert detail.json()["message_count"] == 2


def test_user_cannot_access_other_users_conversation(chat_client):
    client, db_path = chat_client
    token_a = _register(client, "stu_a")
    token_b = _register(client, "stu_b")
    cid = _ask(client, token_a).json()["conversation_id"]

    assert client.get(f"/api/conversations/{cid}", headers=_auth(token_b)).status_code == 404
    assert (
        client.get(
            f"/api/conversations/{cid}/messages", headers=_auth(token_b)
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/conversations/{cid}", headers=_auth(token_b)).status_code
        == 404
    )
    resp = _ask(client, token_b, conversation_id=cid)
    assert resp.status_code == 404

    # 越权请求不能把消息写到 A 的会话里
    assert (
        _rows(
            db_path,
            "SELECT COUNT(*) AS c FROM messages WHERE conversation_id = ?",
            (cid,),
        )[0]["c"]
        == 2
    )


def test_conversation_list_only_own_and_paginates(chat_client):
    client, _ = chat_client
    token_a = _register(client, "stu_a")
    token_b = _register(client, "stu_b")

    c1 = _ask(client, token_a, question="什么是分数").json()["conversation_id"]
    c2 = _ask(client, token_a, question="什么是通分").json()["conversation_id"]
    _ask(client, token_b, question="什么是倍数")

    first = client.get("/api/conversations?limit=1", headers=_auth(token_a))
    assert first.status_code == 200
    page1 = first.json()
    assert len(page1["items"]) == 1
    assert page1["has_more"] is True

    second = client.get(
        f"/api/conversations?limit=1&cursor={page1['next_cursor']}",
        headers=_auth(token_a),
    )
    assert second.status_code == 200
    page2 = second.json()
    assert len(page2["items"]) == 1
    assert {page1["items"][0]["id"], page2["items"][0]["id"]} == {c1, c2}

    all_a = client.get("/api/conversations?limit=20", headers=_auth(token_a)).json()
    assert {i["id"] for i in all_a["items"]} == {c1, c2}


def test_message_pagination_returns_chronological_pages(chat_client):
    client, _ = chat_client
    token = _register(client)
    cid = _ask(client, token, question="什么是分数").json()["conversation_id"]
    _ask(client, token, question="什么是通分", conversation_id=cid)

    newest = client.get(
        f"/api/conversations/{cid}/messages?limit=2", headers=_auth(token)
    )
    assert newest.status_code == 200
    page1 = newest.json()
    assert [m["role"] for m in page1["items"]] == ["user", "assistant"]
    assert page1["has_more"] is True

    older = client.get(
        f"/api/conversations/{cid}/messages?limit=2&cursor={page1['next_cursor']}",
        headers=_auth(token),
    )
    assert older.status_code == 200
    page2 = older.json()
    assert [m["role"] for m in page2["items"]] == ["user", "assistant"]
    assert page2["has_more"] is False

    # 两页拼起来是完整的 4 条，且时间顺序正确
    combined = page2["items"] + page1["items"]
    assert [m["role"] for m in combined] == ["user", "assistant", "user", "assistant"]


def test_client_request_id_is_idempotent(chat_client):
    client, db_path = chat_client
    token = _register(client)

    first = _ask(client, token, client_request_id="req-1")
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["persisted"] is True

    second = _ask(client, token, client_request_id="req-1")
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["deduplicated"] is True
    assert second_data["conversation_id"] == first_data["conversation_id"]
    assert second_data["user_message_id"] == first_data["user_message_id"]
    assert second_data["assistant_message_id"] == first_data["assistant_message_id"]

    assert _rows(db_path, "SELECT COUNT(*) AS c FROM messages")[0]["c"] == 2


def test_generation_failure_is_recorded_and_returns_502(chat_client, monkeypatch):
    client, db_path = chat_client
    token = _register(client)

    def boom(prompt):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(api.generator, "generate", boom)
    resp = _ask(client, token)
    assert resp.status_code == 502
    body = resp.json()
    assert body["error"]["code"] == "UPSTREAM_ERROR"
    assert body["error"]["details"]["conversation_id"]
    assert body["error"]["details"]["assistant_message_id"]

    msgs = _rows(db_path, "SELECT * FROM messages ORDER BY rowid")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["status"] == "failed"
    assert msgs[1]["error_code"] == "UPSTREAM_ERROR"
    assert msgs[1]["content"] is None


def test_refused_question_is_persisted_without_knowledge_points(chat_client):
    client, db_path = chat_client
    token = _register(client)

    resp = _ask(client, token, question="什么是导数")
    assert resp.status_code == 200
    data = resp.json()
    assert data["refused"] is True
    assert data["persisted"] is True

    assistant = _rows(
        db_path,
        "SELECT * FROM messages WHERE role = 'assistant' ORDER BY rowid DESC LIMIT 1",
    )[0]
    assert assistant["refused"] == 1
    assert "当前知识库未覆盖该内容" in assistant["content"]
    assert json.loads(assistant["learning_path_json"]) is None

    kps = _rows(
        db_path,
        "SELECT COUNT(*) AS c FROM message_knowledge_points WHERE message_id = ?",
        (assistant["id"],),
    )
    assert kps[0]["c"] == 0


def test_soft_delete_hides_conversation_but_keeps_messages(chat_client):
    client, db_path = chat_client
    token = _register(client)
    cid = _ask(client, token).json()["conversation_id"]

    deleted = client.delete(f"/api/conversations/{cid}", headers=_auth(token))
    assert deleted.status_code == 204
    assert client.get(f"/api/conversations/{cid}", headers=_auth(token)).status_code == 404

    listed = client.get("/api/conversations", headers=_auth(token)).json()
    assert all(i["id"] != cid for i in listed["items"])
    assert (
        _rows(
            db_path,
            "SELECT COUNT(*) AS c FROM messages WHERE conversation_id = ?",
            (cid,),
        )[0]["c"]
        == 2
    )

    # 重复删除仍幂等返回 204
    assert client.delete(f"/api/conversations/{cid}", headers=_auth(token)).status_code == 204


def test_create_and_get_conversation(chat_client):
    client, _ = chat_client
    token = _register(client)
    created = client.post(
        "/api/conversations",
        json={"title": "新会话标题"},
        headers=_auth(token),
    )
    assert created.status_code == 201
    cid = created.json()["id"]
    assert created.json()["title"] == "新会话标题"
    assert created.json()["message_count"] == 0

    detail = client.get(f"/api/conversations/{cid}", headers=_auth(token))
    assert detail.status_code == 200
    assert detail.json()["id"] == cid


def test_invalid_cursor_returns_400(chat_client):
    client, _ = chat_client
    token = _register(client)
    cid = _ask(client, token).json()["conversation_id"]

    assert (
        client.get(
            "/api/conversations?cursor=not-a-cursor", headers=_auth(token)
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"/api/conversations/{cid}/messages?cursor=not-a-cursor",
            headers=_auth(token),
        ).status_code
        == 400
    )


def test_token_is_not_written_into_messages(chat_client):
    client, db_path = chat_client
    token = _register(client)
    _ask(client, token)

    rows = _rows(
        db_path,
        "SELECT content, knowledge_point, source, learning_path_json, "
        "       prerequisite_gaps_json, error_code, error_message FROM messages",
    )
    assert rows
    for row in rows:
        for key in row.keys():
            value = row[key]
            if isinstance(value, str):
                assert token not in value


def test_request_user_id_is_ignored(chat_client):
    client, db_path = chat_client
    token_a = _register(client, "stu_a")
    token_b = _register(client, "stu_b")
    b_id = _rows(
        db_path, "SELECT id FROM users WHERE username = 'stu_b'"
    )[0]["id"]

    resp = _ask(client, token_a, user_id=b_id)
    assert resp.status_code == 200
    cid = resp.json()["conversation_id"]
    owner = _rows(
        db_path, "SELECT user_id FROM conversations WHERE id = ?", (cid,)
    )[0]["user_id"]
    a_id = _rows(
        db_path, "SELECT id FROM users WHERE username = 'stu_a'"
    )[0]["id"]
    assert owner == a_id
