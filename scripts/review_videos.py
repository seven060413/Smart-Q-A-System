"""命令行审核 B 站视频候选（CLI / CSV）。

用法（项目根目录）：
    # 查看待审
    .venv/Scripts/python.exe scripts/review_videos.py list --status pending

    # 导出待审 CSV，交给老师/助教离线审核
    .venv/Scripts/python.exe scripts/review_videos.py export \
        --status pending --output data/review_5b.csv

    # 通过 / 拒绝
    .venv/Scripts/python.exe scripts/review_videos.py approve \
        --candidate-id 12 --rank 1 --reviewer teacher_a --note "内容匹配"
    .venv/Scripts/python.exe scripts/review_videos.py reject \
        --candidate-id 13 --reviewer teacher_a --note "广告/不匹配"

    # 没有候选时手工加一条并直接通过
    .venv/Scripts/python.exe scripts/review_videos.py add \
        --node-key math_5b_rjb_cpt20 --bvid BV1xx411c7mD \
        --title "分数单位讲解" --reviewer teacher_a
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.schema import _utcnow  # noqa: E402
from src.video_import import (  # noqa: E402
    DEFAULT_COURSE_ID,
    approve_candidate,
    fetch_bilibili_meta,
    node_name_for,
    parse_duration,
    reject_candidate,
    upsert_candidate,
    upsert_video,
)

BOOK_VERSION_ID = "math:book:math_5b_rjb"
EXPORT_FIELDS = [
    "candidate_id",
    "node_key",
    "node_name",
    "bvid",
    "page",
    "title",
    "author",
    "duration_seconds",
    "query",
    "current_status",
    "decision",
    "rank",
    "note",
]


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _list_candidates(
    conn,
    *,
    status: str,
    node_key: str | None,
    graph_version_id: str,
    course_id: str,
    limit: int,
) -> list[dict]:
    sql = (
        "SELECT c.id AS candidate_id, c.node_key, c.bvid, c.page, c.title, "
        "       c.author, c.duration_seconds, c.query, c.fetched_at, "
        "       kpv.review_status, kpv.rank, kpv.reviewed_by, kpv.reviewed_at "
        "FROM video_candidates c "
        "LEFT JOIN knowledge_point_videos kpv "
        "  ON kpv.course_id = c.course_id "
        " AND kpv.node_key = c.node_key "
        " AND kpv.video_id = 'bilibili:' || c.bvid || ':' || c.page "
        " AND kpv.relation = 'explains' "
        "WHERE c.course_id = ?"
    )
    params: list = [course_id]
    if status == "pending":
        sql += " AND (kpv.review_status IS NULL OR kpv.review_status = 'pending')"
    elif status in ("approved", "rejected"):
        sql += " AND kpv.review_status = ?"
        params.append(status)
    if node_key:
        sql += " AND c.node_key = ?"
        params.append(node_key)
    sql += " ORDER BY c.node_key, c.id LIMIT ?"
    params.append(limit)

    items = []
    for row in conn.execute(sql, params).fetchall():
        item = dict(row)
        item["node_name"] = node_name_for(
            conn, row["node_key"], graph_version_id
        )
        item["current_status"] = row["review_status"] or "pending"
        items.append(item)
    return items


def _print_items(items: list[dict]) -> None:
    if not items:
        print("没有符合条件的候选。")
        return
    for item in items:
        duration = item.get("duration_seconds")
        duration_text = f"{duration}s" if duration else "-"
        print(
            f"[{item['candidate_id']}] {item['current_status']:<8} "
            f"{item['node_key']} {item.get('node_name') or ''} | "
            f"{item['bvid']} p{item['page']} | {item.get('title') or ''} | "
            f"{item.get('author') or '-'} | {duration_text} | "
            f"query={item.get('query') or '-'}"
        )


def _export(items: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "candidate_id": item["candidate_id"],
                    "node_key": item["node_key"],
                    "node_name": item.get("node_name") or "",
                    "bvid": item["bvid"],
                    "page": item["page"],
                    "title": item.get("title") or "",
                    "author": item.get("author") or "",
                    "duration_seconds": item.get("duration_seconds") or "",
                    "query": item.get("query") or "",
                    "current_status": item["current_status"],
                    "decision": "",
                    "rank": "",
                    "note": "",
                }
            )


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="B 站视频候选审核")
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--course-id", default=DEFAULT_COURSE_ID)
    parser.add_argument("--graph-version", default=BOOK_VERSION_ID)

    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="列出候选")
    list_parser.add_argument(
        "--status", default="pending", choices=["pending", "approved", "rejected", "all"]
    )
    list_parser.add_argument("--node-key", default=None)
    list_parser.add_argument("--limit", type=int, default=100)

    export_parser = sub.add_parser("export", help="导出 CSV 供离线审核")
    export_parser.add_argument(
        "--status", default="pending", choices=["pending", "approved", "rejected", "all"]
    )
    export_parser.add_argument("--node-key", default=None)
    export_parser.add_argument("--limit", type=int, default=1000)
    export_parser.add_argument("--output", required=True)

    approve_parser = sub.add_parser("approve", help="审核通过候选")
    approve_parser.add_argument("--candidate-id", type=int, required=True)
    approve_parser.add_argument("--rank", type=int, default=0)
    approve_parser.add_argument("--reviewer", required=True)
    approve_parser.add_argument("--note", default=None)
    approve_parser.add_argument(
        "--fetch-meta",
        action="store_true",
        help="调用 B 站公开 view 接口补齐 aid/cid（仅审核阶段联网）",
    )

    reject_parser = sub.add_parser("reject", help="审核拒绝候选")
    reject_parser.add_argument("--candidate-id", type=int, required=True)
    reject_parser.add_argument("--reviewer", required=True)
    reject_parser.add_argument("--note", default=None)

    add_parser = sub.add_parser("add", help="手工新增一条并直接审核通过")
    add_parser.add_argument("--node-key", required=True)
    add_parser.add_argument("--bvid", required=True)
    add_parser.add_argument("--page", type=int, default=1)
    add_parser.add_argument("--aid", type=int, default=None)
    add_parser.add_argument("--cid", type=int, default=None)
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--author", default=None)
    add_parser.add_argument("--duration", default=None)
    add_parser.add_argument("--cover-url", default=None)
    add_parser.add_argument("--query", default="manual")
    add_parser.add_argument("--rank", type=int, default=0)
    add_parser.add_argument("--reviewer", required=True)
    add_parser.add_argument("--note", default=None)
    add_parser.add_argument(
        "--fetch-meta",
        action="store_true",
        help="调用 B 站公开 view 接口补齐 aid/cid（仅审核阶段联网）",
    )

    resolve_parser = sub.add_parser(
        "resolve", help="为已有视频补齐官方嵌入所需的 aid/cid"
    )
    resolve_parser.add_argument("--node-key", default=None)
    resolve_parser.add_argument("--limit", type=int, default=100)
    resolve_parser.add_argument("--interval", type=float, default=2.0)

    args = parser.parse_args()
    conn = db_module.connect(args.db_path)
    try:
        if args.command in ("list", "export"):
            items = _list_candidates(
                conn,
                status=args.status,
                node_key=args.node_key,
                graph_version_id=args.graph_version,
                course_id=args.course_id,
                limit=args.limit,
            )
            if args.command == "list":
                _print_items(items)
            else:
                _export(items, Path(args.output))
                print(f"已导出 {len(items)} 条候选到 {args.output}")
            return

        if args.command == "approve":
            result = approve_candidate(
                conn,
                args.candidate_id,
                reviewer=args.reviewer,
                rank=args.rank,
                note=args.note,
                source_graph_version_id=args.graph_version,
                course_id=args.course_id,
                fetch_meta=args.fetch_meta,
            )
            conn.commit()
            print(
                f"已通过: node={result['node_key']} video={result['video_id']} "
                f"aid={result.get('aid')} cid={result.get('cid')} "
                f"mapping={result['mapping_id']}"
            )
            return

        if args.command == "reject":
            result = reject_candidate(
                conn,
                args.candidate_id,
                reviewer=args.reviewer,
                note=args.note,
                source_graph_version_id=args.graph_version,
                course_id=args.course_id,
            )
            conn.commit()
            print(
                f"已拒绝: node={result['node_key']} video={result['video_id']} "
                f"mapping={result['mapping_id']}"
            )
            return

        if args.command == "resolve":
            sql = (
                "SELECT DISTINCT v.id, v.bvid, v.page FROM videos v "
                "JOIN knowledge_point_videos kpv ON kpv.video_id = v.id "
                "WHERE (v.aid IS NULL OR v.cid IS NULL)"
            )
            params: list = []
            if args.node_key:
                sql += " AND kpv.node_key = ?"
                params.append(args.node_key)
            sql += " ORDER BY v.id LIMIT ?"
            params.append(args.limit)
            rows = conn.execute(sql, params).fetchall()
            if not rows:
                print("没有需要补齐 aid/cid 的视频。")
                return

            ok = 0
            failed = 0
            for index, row in enumerate(rows, start=1):
                try:
                    meta = fetch_bilibili_meta(row["bvid"], row["page"])
                    now = _utcnow()
                    conn.execute(
                        "UPDATE videos SET aid = ?, cid = ?, updated_at = ? "
                        "WHERE id = ?",
                        (meta.get("aid"), meta.get("cid"), now, row["id"]),
                    )
                    conn.execute(
                        "UPDATE video_candidates SET aid = ?, cid = ? "
                        "WHERE bvid = ? AND page = ?",
                        (
                            meta.get("aid"),
                            meta.get("cid"),
                            row["bvid"],
                            row["page"],
                        ),
                    )
                    conn.commit()
                    ok += 1
                    print(
                        f"[{index}/{len(rows)}] {row['bvid']} p{row['page']} "
                        f"aid={meta.get('aid')} cid={meta.get('cid')}"
                    )
                except Exception as exc:
                    failed += 1
                    print(
                        f"[{index}/{len(rows)}] {row['bvid']} p{row['page']} "
                        f"失败: {exc}"
                    )
                if index < len(rows):
                    time.sleep(max(0.0, args.interval))
            print(f"完成: 成功 {ok}，失败 {failed}")
            return

        if args.command == "add":
            aid, cid = args.aid, args.cid
            if args.fetch_meta and (not aid or not cid):
                meta = fetch_bilibili_meta(args.bvid, args.page)
                aid, cid = meta.get("aid"), meta.get("cid")
            video_id = upsert_video(
                conn,
                bvid=args.bvid,
                page=args.page,
                title=args.title,
                author=args.author,
                duration_seconds=parse_duration(args.duration),
                cover_url=args.cover_url,
                aid=aid,
                cid=cid,
                metadata={"source": "manual-add"},
                course_id=args.course_id,
            )
            candidate_id = upsert_candidate(
                conn,
                node_key=args.node_key,
                bvid=args.bvid,
                query=args.query,
                page=args.page,
                aid=aid,
                cid=cid,
                title=args.title,
                author=args.author,
                duration_seconds=parse_duration(args.duration),
                cover_url=args.cover_url,
                raw={"source": "manual-add"},
                course_id=args.course_id,
            )
            result = approve_candidate(
                conn,
                candidate_id,
                reviewer=args.reviewer,
                rank=args.rank,
                note=args.note,
                source_graph_version_id=args.graph_version,
                course_id=args.course_id,
            )
            conn.commit()
            print(
                f"已新增并通过: candidate={candidate_id} "
                f"node={result['node_key']} video={video_id} "
                f"aid={result.get('aid')} cid={result.get('cid')}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
