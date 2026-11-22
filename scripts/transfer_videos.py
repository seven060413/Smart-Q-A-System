"""视频库数据包导出/导入（只涉及 videos 与 knowledge_point_videos）。

用途：
- 本地审核好的视频库需要同步到服务器，但 `data/app/ikgr.db` 不入 Git、不能整库覆盖；
- 本脚本把两张视频表导出成一个 JSON 数据包，在服务器上幂等导入，不影响用户、
  会话、附件等其它数据。

用法（项目根目录）：
    # 本地导出（默认写到 data/exports/videos_transfer.json，该目录不入 Git）
    .venv/Scripts/python.exe scripts/transfer_videos.py export

    # 服务器先 dry-run 看差异，确认后加 --apply
    .venv/bin/python scripts/transfer_videos.py import
    .venv/bin/python scripts/transfer_videos.py import --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402

FORMAT_VERSION = 1
DEFAULT_PACK = ROOT / "data" / "exports" / "videos_transfer.json"

VIDEO_COLUMNS = (
    "id",
    "platform",
    "bvid",
    "page",
    "aid",
    "title",
    "author",
    "duration_seconds",
    "cover_url",
    "watch_url",
    "published_at",
    "status",
    "metadata_json",
    "created_at",
    "updated_at",
    "cid",
)

MAPPING_COLUMNS = (
    "course_id",
    "node_key",
    "node_name",
    "video_id",
    "relation",
    "rank",
    "review_status",
    "review_note",
    "reviewed_by",
    "reviewed_at",
    "source_graph_version_id",
    "created_at",
    "updated_at",
)

VIDEO_UPSERT = f"""
INSERT INTO videos ({", ".join(VIDEO_COLUMNS)})
VALUES ({", ".join("?" for _ in VIDEO_COLUMNS)})
ON CONFLICT(id) DO UPDATE SET
    platform = excluded.platform,
    bvid = excluded.bvid,
    page = excluded.page,
    aid = excluded.aid,
    title = excluded.title,
    author = excluded.author,
    duration_seconds = excluded.duration_seconds,
    cover_url = excluded.cover_url,
    watch_url = excluded.watch_url,
    published_at = excluded.published_at,
    status = excluded.status,
    metadata_json = excluded.metadata_json,
    updated_at = excluded.updated_at,
    cid = excluded.cid
"""

MAPPING_UPSERT = f"""
INSERT INTO knowledge_point_videos ({", ".join(MAPPING_COLUMNS)})
VALUES ({", ".join("?" for _ in MAPPING_COLUMNS)})
ON CONFLICT(course_id, node_key, video_id, relation) DO UPDATE SET
    node_name = excluded.node_name,
    rank = excluded.rank,
    review_status = excluded.review_status,
    review_note = excluded.review_note,
    reviewed_by = excluded.reviewed_by,
    reviewed_at = excluded.reviewed_at,
    source_graph_version_id = excluded.source_graph_version_id,
    updated_at = excluded.updated_at
"""


class TransferError(RuntimeError):
    """数据包不完整或目标库状态不允许导入。"""


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _mapping_key(row: dict) -> tuple:
    return (
        row.get("course_id"),
        row.get("node_key"),
        row.get("video_id"),
        row.get("relation"),
    )


def _row_values(row: dict, columns: tuple) -> tuple:
    missing = [c for c in columns if c not in row]
    if missing:
        raise TransferError(f"数据包字段缺失：{', '.join(missing)}")
    return tuple(row[c] for c in columns)


def export_pack(db_path: str | None, out_path: str | Path = DEFAULT_PACK) -> dict:
    """把当前库的视频表和映射表导出为 JSON 数据包。"""
    conn = db_module.connect(db_path)
    try:
        videos = [
            dict(row)
            for row in conn.execute(
                f"SELECT {', '.join(VIDEO_COLUMNS)} FROM videos ORDER BY id"
            )
        ]
        mappings = [
            dict(row)
            for row in conn.execute(
                f"SELECT {', '.join(MAPPING_COLUMNS)} "
                "FROM knowledge_point_videos "
                "ORDER BY course_id, node_key, video_id, relation"
            )
        ]
    finally:
        conn.close()

    payload = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "counts": {"videos": len(videos), "mappings": len(mappings)},
        "videos": videos,
        "mappings": mappings,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    approved = sum(1 for m in mappings if m.get("review_status") == "approved")
    print(f"已导出 {len(videos)} 条视频、{len(mappings)} 条映射（其中已审核 {approved} 条）")
    print(f"数据包：{out}")
    return payload


def load_pack(path: str | Path) -> dict:
    source = Path(path)
    if not source.exists():
        raise TransferError(f"数据包不存在：{source}")
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise TransferError(f"数据包不是合法 JSON：{exc}") from None
    if payload.get("format_version") != FORMAT_VERSION:
        raise TransferError(
            f"数据包版本不兼容：{payload.get('format_version')}，期望 {FORMAT_VERSION}"
        )
    videos = payload.get("videos")
    mappings = payload.get("mappings")
    if not isinstance(videos, list) or not isinstance(mappings, list):
        raise TransferError("数据包缺少 videos / mappings 数组")

    seen: set[str] = set()
    for row in videos:
        video_id = row.get("id")
        if not video_id or video_id in seen:
            raise TransferError(f"视频 id 缺失或重复：{video_id!r}")
        seen.add(video_id)
    for row in mappings:
        if row.get("video_id") not in seen:
            raise TransferError(
                f"映射引用了数据包中不存在的视频：{row.get('video_id')!r}"
            )
    return payload


def import_pack(
    db_path: str | None,
    pack_path: str | Path = DEFAULT_PACK,
    *,
    apply: bool = False,
) -> dict:
    """把数据包幂等导入目标库；apply=False 时只报告差异。"""
    payload = load_pack(pack_path)
    videos = payload["videos"]
    mappings = payload["mappings"]

    conn = db_module.connect(db_path)
    try:
        # 目标库必须已有 courses 行，否则映射外键会失败；提前给出明确提示。
        course_ids = {
            row["id"] for row in conn.execute("SELECT id FROM courses")
        }
        missing_courses = {
            row.get("course_id") for row in mappings
        } - course_ids
        if missing_courses:
            raise TransferError(
                "目标库缺少课程行："
                + ", ".join(sorted(str(c) for c in missing_courses))
                + "；请先运行 scripts/import_graph.py"
            )

        existing_videos = {
            row["id"]: row
            for row in conn.execute(
                "SELECT id, platform, bvid, page FROM videos"
            )
        }
        existing_mappings = {
            _mapping_key(dict(row))
            for row in conn.execute(
                "SELECT course_id, node_key, video_id, relation "
                "FROM knowledge_point_videos"
            )
        }

        # 同一 (platform,bvid,page) 若已存在但 id 不同，upsert 会撞第二个唯一索引；
        # 与其让 SQLite 报错，不如提前指出冲突。
        conflicts = []
        for row in videos:
            key = (row.get("platform"), row.get("bvid"), row.get("page"))
            for existing_id, existing in existing_videos.items():
                if (
                    existing_id != row.get("id")
                    and (existing["platform"], existing["bvid"], existing["page"]) == key
                ):
                    conflicts.append(f"{existing_id} ↔ {row.get('id')}")
        if conflicts:
            raise TransferError(
                "目标库存在相同平台/bvid/page 但 id 不同的视频，请人工处理："
                + "; ".join(conflicts[:5])
            )

        new_videos = sum(1 for row in videos if row.get("id") not in existing_videos)
        new_mappings = sum(
            1 for row in mappings if _mapping_key(row) not in existing_mappings
        )
        print(
            f"数据包：{len(videos)} 条视频（新增 {new_videos}，更新 "
            f"{len(videos) - new_videos}），{len(mappings)} 条映射（新增 "
            f"{new_mappings}，更新 {len(mappings) - new_mappings}）"
        )

        if not apply:
            print("dry-run：未写库；确认后加 --apply")
            return {
                "applied": False,
                "new_videos": new_videos,
                "new_mappings": new_mappings,
            }

        # 写库前做在线快照，导入出错可按备份回滚。
        resolved = db_module.resolve_db_path(db_path)
        if str(resolved) != ":memory:":
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            snapshot = db_module.backup(
                conn,
                resolved.parent / "backups" / f"ikgr_before_videos_import_{stamp}.db",
            )
            print(f"导入前快照：{snapshot}")

        with conn:
            for row in videos:
                conn.execute(VIDEO_UPSERT, _row_values(row, VIDEO_COLUMNS))
            for row in mappings:
                conn.execute(MAPPING_UPSERT, _row_values(row, MAPPING_COLUMNS))

        total_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        approved_videos = conn.execute(
            "SELECT COUNT(DISTINCT video_id) FROM knowledge_point_videos "
            "WHERE review_status = 'approved'"
        ).fetchone()[0]
        print(
            f"导入完成：库内视频 {total_videos} 条，已审核且关联知识点的视频 "
            f"{approved_videos} 条"
        )
        return {
            "applied": True,
            "new_videos": new_videos,
            "new_mappings": new_mappings,
            "total_videos": total_videos,
            "approved_videos": approved_videos,
        }
    finally:
        conn.close()


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="视频库数据包导出/导入")
    parser.add_argument("command", choices=["export", "import"])
    parser.add_argument("--db", dest="db_path", default=None,
                        help="数据库路径（默认 data/app/ikgr.db，可用 IKGR_DB_PATH 覆盖）")
    parser.add_argument("--out", default=str(DEFAULT_PACK),
                        help="export 输出路径")
    parser.add_argument("--input", default=str(DEFAULT_PACK),
                        help="import 数据包路径")
    parser.add_argument("--apply", action="store_true",
                        help="import 时真正写库；默认 dry-run")
    args = parser.parse_args()

    try:
        if args.command == "export":
            export_pack(args.db_path, args.out)
        else:
            import_pack(args.db_path, args.input, apply=args.apply)
    except TransferError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
