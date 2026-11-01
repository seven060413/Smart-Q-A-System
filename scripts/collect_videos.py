"""离线导入 B 站视频候选（CSV / JSON）。

首期不接实时搜索：B 站搜索接口可能要求 WBI/Cookie，且本仓库没有 BiliLite
源码，无法验证其 searchVideo() 的实现。先支持人工/浏览器辅助整理的 CSV/JSON。

用法（项目根目录）：
    # 1) 导出五年级下册 59 个知识点的空白模板
    .venv/Scripts/python.exe scripts/collect_videos.py --export-seed data/video_candidates_5b.csv

    # 2) 填好 bvid 等字段后导入
    .venv/Scripts/python.exe scripts/collect_videos.py --from-csv data/video_candidates_5b.csv

CSV 表头：
    node_key,bvid,page,title,author,duration_seconds,cover_url,query,play_count,published_at,search_rank

JSON 可以是数组，也可以是 {"items": [...]}。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.errors import ApiError  # noqa: E402
from src.loader import load_nodes  # noqa: E402
from src.subgraph import OUT_PATH  # noqa: E402
from src.video_import import (  # noqa: E402
    DEFAULT_COURSE_ID,
    parse_duration,
    upsert_candidate,
    upsert_video,
)

BOOK_VERSION_ID = "math:book:math_5b_rjb"
CSV_FIELDS = [
    "node_key",
    "node_name",
    "bvid",
    "page",
    "aid",
    "cid",
    "title",
    "author",
    "duration_seconds",
    "cover_url",
    "query",
    "play_count",
    "published_at",
    "search_rank",
]


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _read_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("items", [])
    if not isinstance(data, list):
        raise ValueError("JSON 顶层必须是数组或 {items: [...]}")
    return [item for item in data if isinstance(item, dict)]


def _read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        return _read_json(path)
    return _read_csv(path)


def _int_or_none(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _known_nodes(conn, version_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT node_key FROM graph_nodes WHERE graph_version_id = ?",
        (version_id,),
    ).fetchall()
    return {row["node_key"] for row in rows}


def export_seed(path: Path) -> int:
    """导出五年级下册 Concept/Skill 的空白 CSV 模板。"""
    nodes = [
        n for n in load_nodes(OUT_PATH) if n.label in ("Concept", "Skill")
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for node in nodes:
            writer.writerow({"node_key": node.id, "node_name": node.name})
    return len(nodes)


def import_rows(
    conn,
    rows: list[dict],
    *,
    graph_version_id: str,
    course_id: str,
    dry_run: bool,
) -> dict:
    known = _known_nodes(conn, graph_version_id)
    ok = 0
    skipped = 0
    errors: list[str] = []

    for index, row in enumerate(rows, start=2):
        node_key = str(row.get("node_key") or "").strip()
        bvid = str(row.get("bvid") or "").strip()
        if not node_key or not bvid:
            skipped += 1
            continue
        if known and node_key not in known:
            errors.append(f"第 {index} 行: 节点 {node_key} 不在 {graph_version_id}")
            continue
        try:
            page = max(1, int(row.get("page") or 1))
            aid = _int_or_none(row.get("aid"))
            cid = _int_or_none(row.get("cid"))
            title = str(row.get("title") or bvid).strip()
            query = str(row.get("query") or "manual").strip()
            author = str(row.get("author") or "").strip() or None
            cover_url = str(row.get("cover_url") or "").strip() or None
            published_at = str(row.get("published_at") or "").strip() or None
            if dry_run:
                print(f"[dry-run] {node_key} <- {bvid} p{page} {title}")
                ok += 1
                continue
            upsert_video(
                conn,
                bvid=bvid,
                page=page,
                title=title,
                author=author,
                duration_seconds=parse_duration(row.get("duration_seconds")),
                cover_url=cover_url,
                aid=aid,
                cid=cid,
                published_at=published_at,
                metadata={"source": "csv-import", "query": query},
                course_id=course_id,
            )
            upsert_candidate(
                conn,
                node_key=node_key,
                bvid=bvid,
                query=query,
                page=page,
                aid=aid,
                cid=cid,
                title=title,
                author=author,
                duration_seconds=parse_duration(row.get("duration_seconds")),
                cover_url=cover_url,
                play_count=_int_or_none(row.get("play_count")),
                published_at=published_at,
                search_rank=_int_or_none(row.get("search_rank")),
                raw={"row": row},
                course_id=course_id,
            )
            ok += 1
        except (ValueError, ApiError) as exc:
            errors.append(f"第 {index} 行: {exc}")

    if not dry_run:
        conn.commit()
    return {"ok": ok, "skipped": skipped, "errors": errors}


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="离线导入 B 站视频候选")
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--from-csv", dest="csv_path", default=None)
    parser.add_argument("--from-json", dest="json_path", default=None)
    parser.add_argument(
        "--export-seed",
        dest="export_seed_path",
        default=None,
        help="导出五年级下册知识点空白 CSV 模板",
    )
    parser.add_argument("--course-id", default=DEFAULT_COURSE_ID)
    parser.add_argument("--graph-version", default=BOOK_VERSION_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--search",
        action="store_true",
        help="占位：实时搜索适配器尚未启用（B 站接口可能要求 WBI/Cookie）",
    )
    args = parser.parse_args()

    if args.search:
        print(
            "实时搜索适配器尚未启用。当前请用 --export-seed 生成模板，"
            "人工/浏览器辅助填写 bvid 后用 --from-csv 或 --from-json 导入。\n"
            "原因：B 站搜索接口不是稳定公开 API，可能需要 WBI 签名与 Cookie；"
            "本仓库没有 BiliLite 源码，无法验证其 searchVideo() 是否调用 WBI。"
        )
        return

    if args.export_seed_path:
        count = export_seed(Path(args.export_seed_path))
        print(f"已导出 {count} 个知识点模板: {args.export_seed_path}")
        return

    source = args.csv_path or args.json_path
    if not source:
        parser.error("需要 --from-csv / --from-json，或使用 --export-seed")
    rows = _read_rows(Path(source))
    conn = db_module.connect(args.db_path)
    try:
        result = import_rows(
            conn,
            rows,
            graph_version_id=args.graph_version,
            course_id=args.course_id,
            dry_run=args.dry_run,
        )
    finally:
        conn.close()

    print(f"处理完成: 成功 {result['ok']}，跳过空行 {result['skipped']}")
    for error in result["errors"]:
        print(f"  [跳过] {error}")


if __name__ == "__main__":
    main()
