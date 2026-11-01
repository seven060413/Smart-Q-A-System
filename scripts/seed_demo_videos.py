"""本地演示数据：给五年级下册几个知识点挂一条可播放的 B 站视频。

用途：在没有正式采集/审核数据前，先把「折叠区视频卡 → 查询接口 →
H5 iframe / APK 播放页」链路跑通。

注意：
- 这里默认用的 BV 来自 docs/选题 7操作手册.md 中的演示视频，不是数学教学视频；
- 仅供本地验证，正式上线前请用 scripts/review_videos.py 审核真实教学视频，
  并删除这些 demo-seed 记录。

用法（项目根目录）：
    .venv/Scripts/python.exe scripts/seed_demo_videos.py
    .venv/Scripts/python.exe scripts/seed_demo_videos.py --bvid BV1F8qqYzEbR
    .venv/Scripts/python.exe scripts/seed_demo_videos.py --node-key math_5b_rjb_cpt20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.schema import _utcnow  # noqa: E402

DEFAULT_BVID = "BV1F8qqYzEbR"
# 该演示 BV 的官方嵌入参数（https://api.bilibili.com/x/web-interface/view）
DEFAULT_AID = 113643459058710
DEFAULT_CID = 27315341452
DEFAULT_NODE_KEYS = [
    "math_5b_rjb_cpt20",  # 分数单位（真分数的前置）
    "math_5b_rjb_cpt18",  # 分数的意义（真分数的前置）
    "math_5b_rjb_cpt19",  # 单位1（真分数的前置）
    "math_5b_rjb_cpt29",  # 最小公倍数（通分的前置）
    "math_5b_rjb_cpt27",  # 通分
    "math_5b_rjb_skl9",   # 通分方法（异分母分数加减法的前置，Skill 节点）
]
BOOK_VERSION_ID = "math:book:math_5b_rjb"
COURSE_ID = "math"


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _ensure_course(conn) -> None:
    now = _utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO courses "
        "(id, code, name, subject, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (COURSE_ID, COURSE_ID, "小学数学", "math", now, now),
    )


def _node_names(conn, node_keys: list[str]) -> dict[str, str]:
    placeholders = ",".join("?" for _ in node_keys)
    rows = conn.execute(
        f"SELECT node_key, name FROM graph_nodes "
        f"WHERE graph_version_id = ? AND node_key IN ({placeholders})",
        (BOOK_VERSION_ID, *node_keys),
    ).fetchall()
    return {row["node_key"]: row["name"] for row in rows}


def seed(
    conn, bvid: str, node_keys: list[str], aid: int | None, cid: int | None
) -> tuple[str, list[tuple[str, str]]]:
    now = _utcnow()
    video_id = f"bilibili:{bvid}:1"
    watch_url = f"https://www.bilibili.com/video/{bvid}"
    title = "知识图谱问答系统实战（播放链路演示）"
    author = "B 站演示数据"

    _ensure_course(conn)
    names = _node_names(conn, node_keys)

    with conn:
        conn.execute(
            "INSERT INTO videos "
            "(id, platform, bvid, page, aid, cid, title, author, watch_url, "
            " status, metadata_json, created_at, updated_at) "
            "VALUES (?, 'bilibili', ?, 1, ?, ?, ?, ?, ?, 'active', '{}', ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            " aid = excluded.aid, cid = excluded.cid, "
            " title = excluded.title, author = excluded.author, "
            " watch_url = excluded.watch_url, status = 'active', "
            " updated_at = excluded.updated_at",
            (video_id, bvid, aid, cid, title, author, watch_url, now, now),
        )

        mapped: list[tuple[str, str]] = []
        for rank, node_key in enumerate(node_keys):
            node_name = names.get(node_key)
            if not node_name:
                continue
            conn.execute(
                "INSERT INTO knowledge_point_videos "
                "(course_id, node_key, node_name, video_id, relation, rank, "
                " review_status, review_note, reviewed_by, reviewed_at, "
                " source_graph_version_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'explains', ?, 'approved', ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(course_id, node_key, video_id, relation) DO UPDATE SET "
                " node_name = excluded.node_name, rank = excluded.rank, "
                " review_status = 'approved', review_note = excluded.review_note, "
                " reviewed_by = excluded.reviewed_by, "
                " reviewed_at = excluded.reviewed_at, "
                " source_graph_version_id = excluded.source_graph_version_id, "
                " updated_at = excluded.updated_at",
                (
                    COURSE_ID,
                    node_key,
                    node_name,
                    video_id,
                    rank,
                    "本地播放链路演示数据，正式发布前请替换为审核通过的教学视频",
                    "demo-seed",
                    now,
                    BOOK_VERSION_ID,
                    now,
                    now,
                ),
            )
            mapped.append((node_key, node_name))

    return video_id, mapped


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="写入本地演示视频数据")
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--bvid", default=DEFAULT_BVID, help="B 站 BV 号（默认取文档示例）")
    parser.add_argument("--aid", type=int, default=None, help="B 站 aid；默认 BV 已有内置值")
    parser.add_argument("--cid", type=int, default=None, help="B 站 cid；默认 BV 已有内置值")
    parser.add_argument(
        "--node-key",
        dest="node_keys",
        action="append",
        default=None,
        help="可重复；默认写入五年级下册几个演示节点",
    )
    args = parser.parse_args()

    node_keys = args.node_keys or DEFAULT_NODE_KEYS
    aid = args.aid
    cid = args.cid
    if args.bvid == DEFAULT_BVID:
        aid = DEFAULT_AID if aid is None else aid
        cid = DEFAULT_CID if cid is None else cid
    conn = db_module.connect(args.db_path)
    try:
        video_id, mapped = seed(conn, args.bvid, node_keys, aid, cid)
    finally:
        conn.close()

    print(f"演示视频: {video_id}")
    print(f"已映射 {len(mapped)} 个知识点：")
    for node_key, name in mapped:
        print(f"  - {node_key} {name}")
    print("提示：这些是 demo-seed 数据，正式上线前请用审核流程替换或删除。")


if __name__ == "__main__":
    main()
