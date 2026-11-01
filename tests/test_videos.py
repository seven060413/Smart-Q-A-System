"""阶段 1：知识点视频查询与稳定 ID 暴露测试。"""

import os

import pytest
from fastapi.testclient import TestClient

# 与 test_api/test_chat 保持一致，避免本地 .env 影响。
os.environ.setdefault("QA_MATCH_SCOPE", "full")

from src import api, auth_deps, db as db_module
from src.chat_service import _enrich_message_knowledge_points
from src.errors import ApiError
from src.schema import apply_migrations
from src.security import now_utc
from src.videos import (
    build_embed_url,
    build_watch_url,
    get_videos_for_nodes,
    normalize_node_keys,
)

BV_A = "BV1xx411c7mD"
BV_B = "BV1xx411c7mE"
BV_C = "BV1xx411c7mF"
BV_D = "BV1xx411c7mG"
BV_HIDDEN = "BV1xx411c7mH"


@pytest.fixture
def conn():
    c = db_module.connect(":memory:")
    apply_migrations(c)
    now = now_utc()
    with c:
        c.execute(
            "INSERT INTO courses "
            "(id, code, name, subject, status, created_at, updated_at) "
            "VALUES ('math', 'math', '小学数学', 'math', 'active', ?, ?)",
            (now, now),
        )
    yield c
    c.close()


def _add_video(
    conn, video_id, bvid, *, status="active", page=1, aid=None, cid=None
):
    now = now_utc()
    conn.execute(
        "INSERT INTO videos "
        "(id, platform, bvid, page, aid, cid, title, watch_url, status, "
        " created_at, updated_at) "
        "VALUES (?, 'bilibili', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            video_id,
            bvid,
            page,
            aid,
            cid,
            f"视频 {bvid}",
            f"https://www.bilibili.com/video/{bvid}",
            status,
            now,
            now,
        ),
    )


def _map_video(conn, node_key, video_id, *, status="approved", rank=0, name=None):
    now = now_utc()
    reviewed_at = None if status == "pending" else now
    reviewed_by = None if status == "pending" else "tester"
    conn.execute(
        "INSERT INTO knowledge_point_videos "
        "(course_id, node_key, node_name, video_id, relation, rank, "
        " review_status, reviewed_by, reviewed_at, created_at, updated_at) "
        "VALUES ('math', ?, ?, ?, 'explains', ?, ?, ?, ?, ?, ?)",
        (
            node_key,
            name or node_key,
            video_id,
            rank,
            status,
            reviewed_by,
            reviewed_at,
            now,
            now,
        ),
    )


def test_only_approved_active_and_limit(conn):
    _add_video(conn, "v1", BV_A)
    _add_video(conn, "v2", BV_B)
    _add_video(conn, "v3", BV_C)
    _add_video(conn, "v4", BV_D)
    _add_video(conn, "v5", BV_HIDDEN, status="hidden")
    _map_video(conn, "kp1", "v1", rank=0)
    _map_video(conn, "kp1", "v2", rank=1)
    _map_video(conn, "kp1", "v3", status="pending")
    _map_video(conn, "kp1", "v4", status="rejected")
    _map_video(conn, "kp2", "v5")

    result = get_videos_for_nodes(conn, ["kp1", "kp2"], limit=1)
    assert [item["node_key"] for item in result["items"]] == ["kp1"]
    assert [v["bvid"] for v in result["items"][0]["videos"]] == [BV_A]
    assert result["missing"] == ["kp2"]

    result = get_videos_for_nodes(conn, ["kp1"], limit=2)
    assert [v["bvid"] for v in result["items"][0]["videos"]] == [BV_A, BV_B]


def test_video_dto_contains_aid_cid(conn):
    _add_video(conn, "v1", BV_A, aid=123, cid=456)
    _map_video(conn, "kp1", "v1")

    result = get_videos_for_nodes(conn, ["kp1"])
    video = result["items"][0]["videos"][0]
    assert video["aid"] == 123
    assert video["cid"] == 456
    assert "isOutside=true" in video["embed_url"]
    assert "aid=123" in video["embed_url"]
    assert "cid=456" in video["embed_url"]


def test_empty_and_missing(conn):
    assert get_videos_for_nodes(conn, []) == {"items": [], "missing": []}
    assert get_videos_for_nodes(conn, ["no_such_node"]) == {
        "items": [],
        "missing": ["no_such_node"],
    }


def test_invalid_node_key(conn):
    with pytest.raises(ApiError) as exc:
        get_videos_for_nodes(conn, ["bad-key!"])
    assert exc.value.code == "INVALID_NODE_KEY"


def test_too_many_node_keys():
    with pytest.raises(ApiError) as exc:
        normalize_node_keys([f"kp{i}" for i in range(21)])
    assert exc.value.code == "TOO_MANY_NODE_KEYS"


def test_embed_and_watch_url():
    assert build_embed_url(BV_A, 2) == (
        "https://player.bilibili.com/player.html?isOutside=true"
        f"&bvid={BV_A}&p=2&autoplay=0&danmaku=0"
    )
    assert build_embed_url(BV_A, 2, aid=123, cid=456) == (
        "https://player.bilibili.com/player.html?isOutside=true"
        f"&aid=123&bvid={BV_A}&cid=456&p=2&autoplay=0&danmaku=0"
    )
    assert build_watch_url(BV_A, 2) == (
        f"https://www.bilibili.com/video/{BV_A}?p=2"
    )
    with pytest.raises(ValueError):
        build_embed_url("not-a-bvid")


def test_enrich_old_message_ids_from_knowledge_points():
    payload = {
        "prerequisite_gaps": [{"name": "通分方法", "required": True}],
        "learning_path": {
            "prerequisites": ["通分方法"],
            "body": "异分母分数加减法",
            "consolidation": ["分数加法"],
        },
    }
    by_relation = {
        "body": [{"id": "math_5b_rjb_skl9", "name": "异分母分数加减法"}],
        "prerequisite_required": [
            {"id": "math_5b_rjb_skl8", "name": "通分方法"}
        ],
        "consolidation": [
            {"id": "math_5b_rjb_cpt35", "name": "分数加法"}
        ],
    }

    out = _enrich_message_knowledge_points(payload, by_relation)
    assert out["prerequisite_gaps"][0]["id"] == "math_5b_rjb_skl8"
    assert out["learning_path"]["body_id"] == "math_5b_rjb_skl9"
    assert out["learning_path"]["prerequisite_ids"] == ["math_5b_rjb_skl8"]
    assert out["learning_path"]["consolidation_ids"] == [
        "math_5b_rjb_cpt35"
    ]


@pytest.fixture
def video_client(tmp_path):
    db_path = tmp_path / "videos.db"
    conn = db_module.connect(db_path)
    apply_migrations(conn)
    now = now_utc()
    with conn:
        conn.execute(
            "INSERT INTO courses "
            "(id, code, name, subject, status, created_at, updated_at) "
            "VALUES ('math', 'math', '小学数学', 'math', 'active', ?, ?)",
            (now, now),
        )
        _add_video(conn, "v1", BV_A)
        _map_video(conn, "kp1", "v1")
    conn.close()

    def override_get_db():
        c = db_module.connect(db_path)
        try:
            yield c
        finally:
            c.close()

    api.app.dependency_overrides[auth_deps.get_db] = override_get_db
    with TestClient(api.app) as client:
        yield client
    api.app.dependency_overrides.clear()


def test_video_api_returns_approved(video_client):
    resp = video_client.get(
        "/api/videos", params=[("node_key", "kp1"), ("limit", 1)]
    )
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    data = resp.json()
    assert data["items"][0]["node_key"] == "kp1"
    assert data["items"][0]["videos"][0]["bvid"] == BV_A
    assert data["items"][0]["videos"][0]["embed_url"].startswith(
        "https://player.bilibili.com/"
    )


def test_video_api_rejects_invalid_key(video_client):
    resp = video_client.get("/api/videos", params={"node_key": "bad-key!"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_NODE_KEY"
