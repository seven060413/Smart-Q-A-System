"""写入 6 条已审核示例视频（无需联网，供克隆后从零运行）。

背景：
- `data/app/ikgr.db` 不入库，克隆者按 migrate + import_graph 初始化后没有视频记录；
- 本脚本直接写入已人工审核的 5 下视频及官方嵌入所需的 aid/cid；
- 正式内容请继续用 scripts/review_videos.py 审核替换。

用法（项目根目录，先完成 migrate + import_graph）：
    .venv/Scripts/python.exe scripts/seed_approved_videos.py
    .venv/Scripts/python.exe scripts/seed_approved_videos.py --db data/app/ikgr.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.video_import import (  # noqa: E402
    DEFAULT_COURSE_ID,
    approve_candidate,
    upsert_candidate,
    upsert_video,
)

BOOK_VERSION_ID = "math:book:math_5b_rjb"
REVIEWER = "seed-approved"
QUERY = "seed-approved"

# (node_key, bvid, aid, cid, title, author)
VIDEOS = [
    (
        "math_5b_rjb_cpt18",
        "BV1aK411W7Vg",
        498169739,
        189864798,
        "分数的意义",
        "请叫我邓老师",
    ),
    (
        "math_5b_rjb_cpt19",
        "BV1sw4m1a7nm",
        1105995157,
        1590439436,
        "五年级重难点分数的意义和单位1核心概念，基础牢固才能举一反三",
        "许仙讲数学",
    ),
    (
        "math_5b_rjb_cpt20",
        "BV1SFkRYSEZF",
        113706155379595,
        27503037291,
        "北师大数学 五上第五单元：分数单位",
        "蜜桃女王tao",
    ),
    (
        "math_5b_rjb_cpt27",
        "BV1TAdZYpE4t",
        114340988459968,
        29426912966,
        "小学数学五年级下册第四单元通分",
        "数学老师阿力",
    ),
    (
        "math_5b_rjb_cpt29",
        "BV12B4y1j7dT",
        603891740,
        857915054,
        "小学数学人教版五年级下册精品课最小公倍数.mp4",
        "潇洒秦333",
    ),
    (
        "math_5b_rjb_skl9",
        "BV12L411274K",
        442353645,
        1091039790,
        "五年级下册 约分和通分 短除法",
        "数学朱老师小学号",
    ),
]


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def seed(conn) -> list[dict]:
    results = []
    for node_key, bvid, aid, cid, title, author in VIDEOS:
        upsert_video(
            conn,
            bvid=bvid,
            page=1,
            title=title,
            author=author,
            aid=aid,
            cid=cid,
            metadata={"source": "seed-approved"},
            course_id=DEFAULT_COURSE_ID,
        )
        candidate_id = upsert_candidate(
            conn,
            node_key=node_key,
            bvid=bvid,
            query=QUERY,
            page=1,
            aid=aid,
            cid=cid,
            title=title,
            author=author,
            raw={"source": "seed-approved"},
            course_id=DEFAULT_COURSE_ID,
        )
        result = approve_candidate(
            conn,
            candidate_id,
            reviewer=REVIEWER,
            rank=1,
            note="仓库内置示例视频，正式内容请走 review_videos.py",
            source_graph_version_id=BOOK_VERSION_ID,
            course_id=DEFAULT_COURSE_ID,
        )
        results.append(result)
    conn.commit()
    return results


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="写入 6 条已审核示例视频")
    parser.add_argument("--db", dest="db_path", default=None)
    args = parser.parse_args()

    conn = db_module.connect(args.db_path)
    try:
        results = seed(conn)
    finally:
        conn.close()

    print(f"已写入/更新 {len(results)} 条已审核视频：")
    for item in results:
        print(
            f"  - {item['node_key']}  {item['bvid']}  "
            f"aid={item.get('aid')} cid={item.get('cid')}"
        )
    print("验证: curl \"http://127.0.0.1:18080/api/videos?node_key=math_5b_rjb_cpt18&limit=1\"")


if __name__ == "__main__":
    main()
