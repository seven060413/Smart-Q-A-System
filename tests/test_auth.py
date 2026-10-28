"""阶段 3：学生注册、登录、当前用户、退出与令牌安全测试。"""

import json

import pytest
from fastapi.testclient import TestClient

from src import api, auth_deps, db as db_module, rate_limit, security
from src.schema import apply_migrations


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    """每个测试用独立 SQLite 文件；调低 scrypt 成本并关闭限流，保证测试快且稳定。"""
    db_path = tmp_path / "auth.db"
    conn = db_module.connect(db_path)
    apply_migrations(conn)
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
    rate_limit.reset()

    with TestClient(api.app) as client:
        yield client, db_path

    rate_limit.reset()
    api.app.dependency_overrides.clear()


def _register(client, username="student_one", password="Password123", **extra):
    body = {"username": username, "password": password}
    body.update(extra)
    return client.post("/api/auth/register", json=body)


def _login(client, username="student_one", password="Password123"):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _session_row(db_path, token):
    conn = db_module.connect(db_path)
    try:
        return conn.execute(
            "SELECT * FROM auth_sessions WHERE token_hash = ?",
            (security.token_hash(token),),
        ).fetchone()
    finally:
        conn.close()


def test_register_creates_student_and_returns_token(auth_client):
    client, _ = auth_client
    resp = _register(client, display_name="小明")

    assert resp.status_code == 201
    data = resp.json()
    assert data["token"].startswith("ikgr_")
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "student"
    assert data["user"]["username"] == "student_one"
    assert data["user"]["display_name"] == "小明"
    assert "password" not in resp.text.lower()
    assert "password_hash" not in resp.text


def test_display_name_defaults_to_username(auth_client):
    client, _ = auth_client
    data = _register(client).json()
    assert data["user"]["display_name"] == "student_one"


def test_register_duplicate_username_case_insensitive(auth_client):
    client, _ = auth_client
    assert _register(client, username="Student_One").status_code == 201

    resp = _register(client, username="student_one")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "USERNAME_TAKEN"


def test_register_cannot_create_teacher(auth_client):
    client, _ = auth_client
    # 未知字段 role 被拒绝，不能通过注册接口提权。
    resp = _register(client, role="teacher")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_password_and_token_not_stored_in_plaintext(auth_client):
    client, db_path = auth_client
    password = "Password123"
    data = _register(client, password=password).json()
    token = data["token"]

    conn = db_module.connect(db_path)
    try:
        user = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("student_one",)
        ).fetchone()
        assert user is not None
        assert user["password_hash"].startswith("scrypt$")
        assert password not in user["password_hash"]

        hashes = [
            r["token_hash"]
            for r in conn.execute("SELECT token_hash FROM auth_sessions").fetchall()
        ]
        assert token not in hashes
        assert security.token_hash(token) in hashes
    finally:
        conn.close()


def test_password_hash_has_random_salt(auth_client):
    # 同一个密码两次哈希结果不同（随机盐），但都能校验通过。
    h1 = security.hash_password("Password123")
    h2 = security.hash_password("Password123")
    assert h1 != h2
    assert security.verify_password("Password123", h1)
    assert security.verify_password("Password123", h2)


def test_login_success_and_me(auth_client):
    client, _ = auth_client
    _register(client)

    resp = _login(client, username="student_one", password="Password123")
    assert resp.status_code == 200
    data = resp.json()
    token = data["token"]

    me = client.get("/api/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == "student_one"
    assert me.json()["role"] == "student"
    assert "password" not in me.text.lower()


def test_login_case_insensitive(auth_client):
    client, _ = auth_client
    _register(client, username="Student_One")
    resp = _login(client, username="student_one")
    assert resp.status_code == 200


def test_login_failure_does_not_reveal_account_existence(auth_client):
    client, _ = auth_client
    _register(client)

    wrong = _login(client, password="WrongPassword")
    missing = _login(client, username="nobody_here", password="WrongPassword")

    assert wrong.status_code == 401
    assert missing.status_code == 401
    assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert missing.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert wrong.json()["error"]["message"] == missing.json()["error"]["message"]


def test_me_requires_token(auth_client):
    client, _ = auth_client
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=_auth("bad-token")).status_code == 401


def test_me_ignores_client_supplied_user_id(auth_client):
    client, _ = auth_client
    a = _register(client, username="user_a").json()
    b = _register(client, username="user_b").json()

    resp = client.get(
        f"/api/auth/me?user_id={b['user']['id']}",
        headers=_auth(a["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "user_a"
    assert resp.json()["id"] == a["user"]["id"]


def test_logout_revokes_and_is_idempotent(auth_client):
    client, _ = auth_client
    token = _register(client).json()["token"]

    assert client.post("/api/auth/logout", headers=_auth(token)).status_code == 204
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401
    # 已撤销的令牌再次退出仍返回 204，不泄露状态。
    assert client.post("/api/auth/logout", headers=_auth(token)).status_code == 204


def test_logout_only_current_device(auth_client):
    client, _ = auth_client
    first = _register(client).json()["token"]
    second = _login(client).json()["token"]

    assert client.post("/api/auth/logout", headers=_auth(first)).status_code == 204
    assert client.get("/api/auth/me", headers=_auth(first)).status_code == 401
    assert client.get("/api/auth/me", headers=_auth(second)).status_code == 200


def test_expired_token_rejected(auth_client):
    client, db_path = auth_client
    token = _register(client).json()["token"]

    conn = db_module.connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE auth_sessions SET expires_at = ? WHERE token_hash = ?",
                ("2000-01-01T00:00:00.000Z", security.token_hash(token)),
            )
    finally:
        conn.close()

    resp = client.get("/api/auth/me", headers=_auth(token))
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_disabled_account_cannot_login(auth_client):
    client, db_path = auth_client
    _register(client)

    conn = db_module.connect(db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE users SET status = 'disabled' WHERE username = ?",
                ("student_one",),
            )
    finally:
        conn.close()

    resp = _login(client)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_DISABLED"


def test_validation_error_does_not_echo_password(auth_client):
    client, _ = auth_client
    secret_value = "S3cr3t!"
    resp = _register(client, password=secret_value)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    # 校验错误不能把请求里的密码原样回显。
    assert secret_value not in resp.text


def test_session_row_is_created(auth_client):
    client, db_path = auth_client
    data = _register(client).json()
    row = _session_row(db_path, data["token"])
    assert row is not None
    assert row["revoked_at"] is None
    assert row["expires_at"] > row["created_at"]


def test_register_rate_limit(auth_client, monkeypatch):
    client, _ = auth_client
    # fixture 默认关闭限流；这里临时开启并只允许 1 次/小时。
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AUTH_REGISTER_LIMIT", "1")
    monkeypatch.setenv("AUTH_REGISTER_WINDOW_SECONDS", "3600")
    rate_limit.reset()

    assert _register(client, username="limit_one").status_code == 201
    resp = _register(client, username="limit_two")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"
    assert resp.headers.get("Retry-After")


def test_login_failure_rate_limit(auth_client, monkeypatch):
    client, _ = auth_client
    _register(client)
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AUTH_LOGIN_FAILURE_LIMIT", "1")
    monkeypatch.setenv("AUTH_LOGIN_WINDOW_SECONDS", "900")
    rate_limit.reset()

    assert _login(client, password="WrongPassword").status_code == 401
    resp = _login(client, password="WrongPassword")
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"
