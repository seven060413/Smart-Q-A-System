"""知识点关联视频的读取服务。

运行时只查本地 SQLite，不访问 B 站、不调用大模型：
- 只返回 review_status='approved' 且 videos.status='active' 的记录；
- 按 node_key 批量查询，避免前端展开前置知识时产生 N 次请求；
- 官方嵌入 URL 与观看 URL 由 bvid/page 统一生成，不信任数据库里的任意 URL。
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from .errors import ApiError

logger = logging.getLogger("ikgr.videos")

DEFAULT_COURSE_ID = "math"
DEFAULT_LIMIT = 2
MAX_LIMIT = 5
MAX_NODE_KEYS = 20
NODE_KEY_MAX_LEN = 128

# 例：BV1xx411c7mD（BV + 10 位）
_BVID_RE = re.compile(r"^BV[0-9A-Za-z]{10}$")
_NODE_KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")

_PLAYER_URL = "https://player.bilibili.com/player.html"
_WATCH_URL = "https://www.bilibili.com/video"


def build_embed_url(
    bvid: str,
    page: int = 1,
    aid: int | None = None,
    cid: int | None = None,
) -> str:
    """生成 B 站官方嵌入播放器 URL。

    官方嵌入代码格式：
    https://player.bilibili.com/player.html?isOutside=true&aid=...&bvid=...&cid=...&p=1
    aid/cid 缺失时退化为仅 bvid + p，仍带 isOutside=true。
    """
    value = (bvid or "").strip()
    if not _BVID_RE.fullmatch(value):
        raise ValueError("invalid bvid")
    page = max(1, int(page or 1))

    parts = ["isOutside=true"]
    if aid:
        parts.append(f"aid={int(aid)}")
    parts.append(f"bvid={value}")
    if cid:
        parts.append(f"cid={int(cid)}")
    parts.extend([f"p={page}", "autoplay=0", "danmaku=0"])
    return f"{_PLAYER_URL}?{'&'.join(parts)}"


def build_watch_url(bvid: str, page: int = 1) -> str:
    """生成 B 站观看页 URL；bvid 非法时抛 ValueError。"""
    value = (bvid or "").strip()
    if not _BVID_RE.fullmatch(value):
        raise ValueError("invalid bvid")
    page = max(1, int(page or 1))
    suffix = f"?p={page}" if page > 1 else ""
    return f"{_WATCH_URL}/{value}{suffix}"


def normalize_node_keys(node_keys: Iterable[str] | None) -> list[str]:
    """去重、校验并限制一次查询的知识点数量。"""
    result: list[str] = []
    seen: set[str] = set()
    for raw in node_keys or []:
        key = (raw or "").strip()
        if not key:
            continue
        if len(key) > NODE_KEY_MAX_LEN or not _NODE_KEY_RE.fullmatch(key):
            raise ApiError(400, "INVALID_NODE_KEY", "知识点编号不合法")
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    if len(result) > MAX_NODE_KEYS:
        raise ApiError(
            400,
            "TOO_MANY_NODE_KEYS",
            f"一次最多查询 {MAX_NODE_KEYS} 个知识点",
        )
    return result


def _row_to_video(row) -> dict | None:
    """把查询行转成前端 DTO；bvid 异常的脏数据跳过并记日志。"""
    try:
        embed_url = build_embed_url(
            row["bvid"], row["page"], row["aid"], row["cid"]
        )
        watch_url = build_watch_url(row["bvid"], row["page"])
    except (TypeError, ValueError):
        logger.warning(
            "skip invalid video row video_id=%s bvid=%r page=%r",
            row["video_id"],
            row["bvid"],
            row["page"],
        )
        return None

    return {
        "video_id": row["video_id"],
        "platform": row["platform"],
        "bvid": row["bvid"],
        "aid": row["aid"],
        "cid": row["cid"],
        "page": row["page"],
        "title": row["title"],
        "author": row["author"],
        "duration_seconds": row["duration_seconds"],
        "cover_url": row["cover_url"],
        "watch_url": watch_url,
        "embed_url": embed_url,
    }


def get_videos_for_nodes(
    conn,
    node_keys: Iterable[str] | None,
    *,
    course_id: str = DEFAULT_COURSE_ID,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """批量查询知识点已审核视频。

    返回 ``{"items": [{node_key, node_name, videos: [...]}], "missing": [...]}``。
    ``missing`` 是没有可用视频的 node_key，前端据此显示空状态。
    """
    keys = normalize_node_keys(node_keys)
    try:
        per_node = int(limit)
    except (TypeError, ValueError):
        per_node = DEFAULT_LIMIT
    per_node = max(1, min(MAX_LIMIT, per_node))

    if not keys:
        return {"items": [], "missing": []}

    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"""
        SELECT kpv.node_key, kpv.node_name, kpv.rank,
               v.id AS video_id, v.platform, v.bvid, v.aid, v.cid, v.page,
               v.title, v.author, v.duration_seconds, v.cover_url
        FROM knowledge_point_videos kpv
        JOIN videos v ON v.id = kpv.video_id
        WHERE kpv.course_id = ?
          AND kpv.review_status = 'approved'
          AND v.status = 'active'
          AND kpv.node_key IN ({placeholders})
        ORDER BY kpv.node_key, kpv.rank, v.id
        """,
        (course_id, *keys),
    ).fetchall()

    grouped: dict[str, list[dict]] = {key: [] for key in keys}
    seen_videos: dict[str, set[str]] = {key: set() for key in keys}
    node_names: dict[str, str] = {}

    for row in rows:
        key = row["node_key"]
        if len(grouped[key]) >= per_node:
            continue
        if row["video_id"] in seen_videos[key]:
            continue
        video = _row_to_video(row)
        if video is None:
            continue
        grouped[key].append(video)
        seen_videos[key].add(row["video_id"])
        if row["node_name"] and key not in node_names:
            node_names[key] = row["node_name"]

    items = [
        {
            "node_key": key,
            "node_name": node_names.get(key, ""),
            "videos": grouped[key],
        }
        for key in keys
        if grouped[key]
    ]
    missing = [key for key in keys if not grouped[key]]
    return {"items": items, "missing": missing}
