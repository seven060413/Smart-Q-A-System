"""阶段 2：候选导入与审核逻辑测试。"""

import pytest

from src import db as db_module
from src.schema import apply_migrations
from src.video_import import (
    approve_candidate,
    parse_duration,
    reject_candidate,
    upsert_candidate,
    upsert_mapping,
)
from src.videos import get_videos_for_nodes

BV_A = "BV1xx411c7mD"


@pytest.fixture
def conn():
    c = db_module.connect(":memory:")
    apply_migrations(c)
    yield c
    c.close()


def test_parse_duration():
    assert parse_duration(480) == 480
    assert parse_duration("8:00") == 480
    assert parse_duration("1:02:03") == 3723
    assert parse_duration("bad") is None


def test_approve_and_reject_keep_video_metadata(conn):
    cid1 = upsert_candidate(
        conn,
        node_key="kp1",
        bvid=BV_A,
        query="manual",
        title="正式标题",
        duration_seconds=480,
    )
    approve_candidate(conn, cid1, reviewer="teacher", rank=1, note="ok")
    conn.commit()

    video = conn.execute(
        "SELECT title, duration_seconds FROM videos WHERE id = ?",
        (f"bilibili:{BV_A}:1",),
    ).fetchone()
    assert video["title"] == "正式标题"
    assert video["duration_seconds"] == 480

    cid2 = upsert_candidate(
        conn,
        node_key="kp2",
        bvid=BV_A,
        query="manual2",
        title="拒绝候选标题",
        duration_seconds=360,
    )
    reject_candidate(conn, cid2, reviewer="teacher", note="不匹配")
    conn.commit()

    # 拒绝候选不能覆盖已通过视频的元数据。
    video = conn.execute(
        "SELECT title, duration_seconds FROM videos WHERE id = ?",
        (f"bilibili:{BV_A}:1",),
    ).fetchone()
    assert video["title"] == "正式标题"
    assert video["duration_seconds"] == 480

    rows = conn.execute(
        "SELECT node_key, review_status FROM knowledge_point_videos "
        "ORDER BY node_key"
    ).fetchall()
    assert [(r["node_key"], r["review_status"]) for r in rows] == [
        ("kp1", "approved"),
        ("kp2", "rejected"),
    ]

    result = get_videos_for_nodes(conn, ["kp1", "kp2"])
    assert [item["node_key"] for item in result["items"]] == ["kp1"]
    assert result["missing"] == ["kp2"]


def test_mapping_requires_reviewer_when_not_pending(conn):
    upsert_candidate(
        conn,
        node_key="kp1",
        bvid=BV_A,
        query="manual",
        title="标题",
    )
    conn.commit()
    with pytest.raises(ValueError):
        upsert_mapping(
            conn,
            node_key="kp1",
            video_id=f"bilibili:{BV_A}:1",
            status="approved",
            reviewer=None,
        )
