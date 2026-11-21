"""阶段 1：知识点视频查询与稳定 ID 暴露测试。"""

import json
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
    list_videos_library,
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
        f"&bvid={BV_A}&p=2&page=2&autoplay=0&danmaku=0&hideCoverInfo=1"
    )
    assert build_embed_url(BV_A, 2, aid=123, cid=456) == (
        "https://player.bilibili.com/player.html?isOutside=true"
        f"&aid=123&bvid={BV_A}&cid=456&p=2&page=2&autoplay=0&danmaku=0&hideCoverInfo=1"
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


def _set_video_meta(conn, video_id, *, title=None, author=None, grade=None, chapter=None):
    if title is not None:
        conn.execute("UPDATE videos SET title = ? WHERE id = ?", (title, video_id))
    if author is not None:
        conn.execute("UPDATE videos SET author = ? WHERE id = ?", (author, video_id))
    meta = {}
    if grade:
        meta["grade"] = grade
    if chapter:
        meta["chapter"] = chapter
    conn.execute(
        "UPDATE videos SET metadata_json = ? WHERE id = ?",
        (json.dumps(meta, ensure_ascii=False), video_id),
    )


def test_library_search_filter_and_pagination(conn):
    _add_video(conn, "v1", BV_A)
    _set_video_meta(
        conn, "v1", title="1.1 正数与负数", author="大舅物理",
        grade="七年级", chapter="第一章 有理数",
    )
    _map_video(conn, "math_7a_rjb_cpt1", "v1", name="正数")

    _add_video(conn, "v2", BV_B)
    _set_video_meta(
        conn, "v2", title="5.1 相交线", author="大舅物理",
        grade="七年级", chapter="第五章 相交线与平行线",
    )
    _map_video(conn, "math_7b_rjb_cpt1", "v2", name="相交线")

    _add_video(conn, "v3", BV_C)
    conn.execute("UPDATE videos SET title = '示例视频' WHERE id = 'v3'")
    _map_video(conn, "math_5b_rjb_cpt18", "v3", name="通分")

    result = list_videos_library(conn)
    assert result["total"] == 3
    assert [item["video_id"] for item in result["items"]] == ["v1", "v2", "v3"]
    assert result["items"][0]["book"] == "七上"
    assert result["items"][1]["book"] == "七下"
    assert result["items"][2]["book"] == "示例"
    assert result["items"][2]["chapter"] == "五年级下册 · 示例视频"
    assert result["items"][0]["knowledge_points"] == ["正数"]
    assert result["facets"]["books"][0] == {"key": "七上", "count": 1}
    assert result["facets"]["books"][1] == {"key": "七下", "count": 1}
    assert result["facets"]["total_all"] == 3

    # 搜索：标题 / UP主 / 知识点；不匹配章节名
    assert list_videos_library(conn, q="正数")["total"] == 1
    assert list_videos_library(conn, q="大舅物理")["total"] == 2
    assert list_videos_library(conn, q="相交线")["total"] == 1
    assert list_videos_library(conn, q="第一章")["total"] == 0

    # 教材册筛选
    only_7a = list_videos_library(conn, book="七上")
    assert only_7a["total"] == 1
    assert only_7a["items"][0]["video_id"] == "v1"

    # 分页
    page1 = list_videos_library(conn, page=1, page_size=1)
    page2 = list_videos_library(conn, page=2, page_size=1)
    assert [item["video_id"] for item in page1["items"]] == ["v1"]
    assert [item["video_id"] for item in page2["items"]] == ["v2"]


def test_library_only_approved_active(conn):
    _add_video(conn, "v1", BV_A)
    _set_video_meta(conn, "v1", title="已审核", chapter="第一章 有理数")
    _map_video(conn, "kp1", "v1")

    _add_video(conn, "v2", BV_B, status="hidden")
    _map_video(conn, "kp1", "v2")

    _add_video(conn, "v3", BV_C)
    _map_video(conn, "kp1", "v3", status="pending")

    result = list_videos_library(conn)
    assert result["total"] == 1
    assert result["items"][0]["video_id"] == "v1"


def test_library_invalid_book(conn):
    with pytest.raises(ApiError) as exc:
        list_videos_library(conn, book="五上")
    assert exc.value.code == "INVALID_BOOK"


def test_video_library_api(video_client):
    resp = video_client.get(
        "/api/videos/library", params={"page": 1, "page_size": 20}
    )
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["video_id"] == "v1"
    assert data["items"][0]["embed_url"].startswith("https://player.bilibili.com/")
    assert data["facets"]["books"][0]["key"] == "七上"


def test_video_library_api_rejects_invalid_book(video_client):
    resp = video_client.get("/api/videos/library", params={"book": "五上"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_BOOK"
