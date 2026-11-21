"""自律事项 AI 整理：鉴权、限流、输出校验与本地规则兜底。"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src import api, auth_deps, db as db_module, rate_limit, selfdiscipline_api
from src.selfdiscipline_parser import ParseResult, normalize_items, parse_locally
from src.schema import apply_migrations


@pytest.fixture
def sd_client(tmp_path, monkeypatch):
    db_path = tmp_path / "selfdiscipline.db"
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
        token = client.post(
            "/api/auth/register",
            json={"username": "sd_user", "password": "Password123"},
        ).json()["token"]
        yield client, token

    rate_limit.reset()
    api.app.dependency_overrides.clear()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class FakeParser:
    def __init__(self, items=None):
        self.items = items or [
            {
                "title": "背单词",
                "note": "20个",
                "kind": "daily",
                "days": [1, 2, 3, 4, 5, 6, 7],
                "date": "",
                "remind_time": "09:00",
                "enabled": True,
                "confidence": 0.9,
            }
        ]

    def parse(self, text, *, today, weekday, now, timezone):
        return ParseResult(items=self.items, reply="整理好了", source="ai")


def test_requires_login(sd_client):
    client, _ = sd_client
    resp = client.post("/api/selfdiscipline/parse-items", json={"text": "每天9点背单词"})
    assert resp.status_code == 401


def test_parse_items_success(sd_client):
    client, token = sd_client
    api.app.dependency_overrides[selfdiscipline_api.get_parser] = lambda: FakeParser()

    resp = client.post(
        "/api/selfdiscipline/parse-items",
        json={"text": "每天9点背20个单词", "today": "2026-11-21", "weekday": 6},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "ai"
    assert data["intent"] == "create"
    assert data["reply"] == "整理好了"
    assert data["items"][0]["title"] == "背单词"
    assert data["items"][0]["remind_time"] == "09:00"
    assert data["items"][0]["days"] == [1, 2, 3, 4, 5, 6, 7]


def test_non_task_intent_returns_empty_items(sd_client):
    client, token = sd_client

    class CancelParser:
        def parse(self, text, *, today, weekday, now, timezone):
            return ParseResult(items=[], reply="好，那不加了。", source="ai", intent="cancel")

    api.app.dependency_overrides[selfdiscipline_api.get_parser] = lambda: CancelParser()

    resp = client.post(
        "/api/selfdiscipline/parse-items",
        json={"text": "不用了"},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["intent"] == "cancel"
    assert data["reply"] == "好，那不加了。"


def test_blank_text_rejected(sd_client):
    client, token = sd_client
    api.app.dependency_overrides[selfdiscipline_api.get_parser] = lambda: FakeParser()

    resp = client.post(
        "/api/selfdiscipline/parse-items",
        json={"text": "   "},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_rate_limited_per_user(sd_client, monkeypatch):
    client, token = sd_client
    api.app.dependency_overrides[selfdiscipline_api.get_parser] = lambda: FakeParser()
    monkeypatch.setenv("AUTH_RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("SD_PARSE_RATE_LIMIT", "1")
    monkeypatch.setenv("SD_PARSE_RATE_WINDOW_SECONDS", "600")
    rate_limit.reset()

    first = client.post(
        "/api/selfdiscipline/parse-items",
        json={"text": "每天9点背单词"},
        headers=_auth(token),
    )
    second = client.post(
        "/api/selfdiscipline/parse-items",
        json={"text": "每天9点背单词"},
        headers=_auth(token),
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_normalize_items_drops_invalid_and_duplicates():
    today = date(2026, 11, 21)
    raw = [
        {"title": " 背单词 ", "repeat": "daily", "days": [1, "三", 9], "remind_time": "9:00"},
        {"title": "背单词", "repeat": "daily", "days": [1, 2], "remind_time": "09:00"},
        {"title": "交作业", "repeat": "once", "date": "2099-01-01", "remind_time": "10点前"},
        {"title": "   ", "repeat": "once"},
    ]

    items = normalize_items(raw, today)

    assert len(items) == 2
    assert items[0]["kind"] == "daily"
    assert items[0]["days"] == [1, 3]
    assert items[0]["remind_time"] == "09:00"
    assert items[1]["kind"] == "once"
    assert items[1]["date"] == today.isoformat()
    assert items[1]["remind_time"] == ""


def test_local_parser_non_task_does_not_create_items():
    today = date(2026, 11, 21)
    for text in ("不用了", "算了", "取消", "不做了", "谢谢", "你好"):
        items, reply, intent = parse_locally(text, today)
        assert items == []
        assert intent in {"cancel", "chat"}
        assert reply


def test_local_parser_daily_and_workday():
    today = date(2026, 11, 21)
    items, _, _ = parse_locally("每天9点背单词；工作日7:30跑步", today)

    assert len(items) == 2
    assert items[0]["kind"] == "daily"
    assert items[0]["days"] == [1, 2, 3, 4, 5, 6, 7]
    assert items[0]["remind_time"] == "09:00"
    assert items[0]["title"] == "背单词"
    assert items[1]["days"] == [1, 2, 3, 4, 5]
    assert items[1]["remind_time"] == "07:30"
    assert items[1]["title"] == "跑步"


def test_local_parser_once_and_weekly():
    today = date(2026, 11, 21)
    items, _, _ = parse_locally("明天晚上8点交作业", today)
    assert items[0]["kind"] == "once"
    assert items[0]["date"] == (today + timedelta(days=1)).isoformat()
    assert items[0]["remind_time"] == "20:00"
    assert items[0]["title"] == "交作业"

    items, _, _ = parse_locally("每周一、周三晚上10点背单词", today)
    assert items[0]["kind"] == "daily"
    assert items[0]["days"] == [1, 3]
    assert items[0]["remind_time"] == "22:00"
    assert items[0]["title"] == "背单词"
