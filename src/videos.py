"""知识点关联视频的读取服务。

运行时只查本地 SQLite，不访问 B 站、不调用大模型：
- 只返回 review_status='approved' 且 videos.status='active' 的记录；
- 按 node_key 批量查询，避免前端展开前置知识时产生 N 次请求；
- 官方嵌入 URL 与观看 URL 由 bvid/page 统一生成，不信任数据库里的任意 URL。
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
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

# 视频库的 6 个教材册筛选（人教版初中数学）。
LIBRARY_BOOKS = ("七上", "七下", "八上", "八下", "九上", "九下")
_BOOK_ORDER = {name: index for index, name in enumerate(LIBRARY_BOOKS)}
_BOOK_ORDER.update({"示例": 90, "其他": 99})
_CN_DIGITS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}


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

    hideCoverInfo=1：移动端播放器会显示合集总时长/播放量，容易被误认为
    整条合集；隐藏封面信息后只保留当前分P 的播放界面。
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
    parts.extend([
        f"p={page}", f"page={page}", "autoplay=0", "danmaku=0",
        "hideCoverInfo=1",
    ])
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


def _https_url(url: str | None) -> str:
    """封面等静态资源统一升级为 https，避免 HTTPS 页面混合内容拦截。"""
    value = (url or "").strip()
    if value.startswith("http://"):
        return "https://" + value[len("http://"):]
    if value.startswith("//"):
        return "https:" + value
    return value


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
        "cover_url": _https_url(row["cover_url"]),
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
        ORDER BY kpv.node_key, kpv.rank,
                 CAST(v.page AS INTEGER), v.id
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


def _cn_to_int(text: str) -> int:
    """把「一」~「二十九」转成整数（视频库章节排序用）。"""
    if not text:
        return 0
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return _CN_DIGITS.get(text, 0)


def _chapter_number(chapter: str) -> int:
    match = re.match(r"第([一二三四五六七八九十]+)章", (chapter or "").strip())
    return _cn_to_int(match.group(1)) if match else 0


def _book_for_chapter(chapter: str) -> str:
    """按人教版初中数学章节号推断教材册：1-4 七上，5-10 七下，以此类推。"""
    number = _chapter_number(chapter)
    if 1 <= number <= 4:
        return "七上"
    if 5 <= number <= 10:
        return "七下"
    if 11 <= number <= 15:
        return "八上"
    if 16 <= number <= 20:
        return "八下"
    if 21 <= number <= 25:
        return "九上"
    if 26 <= number <= 29:
        return "九下"
    return ""


def _library_item(row, node_names: list[str]) -> dict | None:
    """把一行视频转成视频库 DTO；bvid 异常时跳过。"""
    bvid = row["bvid"]
    page = max(1, int(row["page"] or 1))
    try:
        embed_url = build_embed_url(bvid, page, row["aid"], row["cid"])
        watch_url = build_watch_url(bvid, page)
    except (TypeError, ValueError):
        logger.warning("skip invalid library video id=%s bvid=%r", row["video_id"], bvid)
        return None

    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except (TypeError, ValueError):
        meta = {}

    chapter = (meta.get("chapter") or "").strip()
    book = _book_for_chapter(chapter)
    if not book:
        if meta.get("grade"):
            book = "其他"
            chapter = chapter or "未分类"
        else:
            # 6 条五年级下册示例视频：没有 grade/chapter 元数据，单独归到示例组。
            book = "示例"
            chapter = chapter or "五年级下册 · 示例视频"

    # 去重但保留插入顺序
    points = list(dict.fromkeys(name for name in node_names if name))
    return {
        "video_id": row["video_id"],
        "platform": row["platform"],
        "bvid": bvid,
        "aid": row["aid"],
        "cid": row["cid"],
        "page": page,
        "title": row["title"],
        "author": row["author"],
        "duration_seconds": row["duration_seconds"],
        "cover_url": _https_url(row["cover_url"]),
        "watch_url": watch_url,
        "embed_url": embed_url,
        "book": book,
        "chapter": chapter,
        "knowledge_points": points,
    }


def list_videos_library(
    conn,
    *,
    q: str = "",
    book: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """视频讲解库：全部已审核视频，支持标题/知识点/UP主搜索和教材册筛选。

    - 只返回 approved + active；
    - 按 video_id 天然去重（一个视频可映射多个知识点）；
    - 搜索只匹配标题、UP主、知识点名称，不匹配章节/年级文本；
    - 返回 facets.books / facets.chapters 供前端筛选和分组。
    """
    q = (q or "").strip()
    book = (book or "").strip()
    if book and book not in LIBRARY_BOOKS:
        raise ApiError(400, "INVALID_BOOK", "教材册筛选不合法")
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(50, int(page_size)))
    except (TypeError, ValueError):
        page_size = 20

    rows = conn.execute(
        """
        SELECT v.id AS video_id, v.platform, v.bvid, v.aid, v.cid, v.page,
               v.title, v.author, v.duration_seconds, v.cover_url, v.metadata_json
        FROM videos v
        WHERE v.status = 'active'
          AND EXISTS (
            SELECT 1 FROM knowledge_point_videos k
            WHERE k.video_id = v.id AND k.review_status = 'approved'
          )
        """
    ).fetchall()

    node_rows = conn.execute(
        """
        SELECT video_id, node_name
        FROM knowledge_point_videos
        WHERE review_status = 'approved'
        GROUP BY video_id, node_name
        """
    ).fetchall()
    node_map: dict[str, list[str]] = {}
    for row in node_rows:
        node_map.setdefault(row["video_id"], []).append(row["node_name"] or "")

    items: list[dict] = []
    needle = q.lower()
    for row in rows:
        names = node_map.get(row["video_id"], [])
        item = _library_item(row, names)
        if item is None:
            continue
        if needle:
            haystack = f"{item['title'] or ''} {item['author'] or ''} {' '.join(names)}".lower()
            if needle not in haystack:
                continue
        items.append(item)

    book_counts = Counter(item["book"] for item in items)
    chapter_counts = Counter((item["book"], item["chapter"]) for item in items)

    if book:
        items = [item for item in items if item["book"] == book]

    items.sort(
        key=lambda item: (
            _BOOK_ORDER.get(item["book"], 99),
            _chapter_number(item["chapter"]),
            item["page"],
            item["video_id"],
        )
    )

    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]
    facets = {
        # 不带 book 筛选时的全量计数（含示例/其他），供“全部”筛选角标使用。
        "total_all": sum(book_counts.values()),
        "books": [
            {"key": name, "count": book_counts.get(name, 0)}
            for name in LIBRARY_BOOKS
        ],
        "chapters": [
            {"book": book_name, "chapter": chapter, "count": count}
            for (book_name, chapter), count in sorted(
                chapter_counts.items(),
                key=lambda kv: (
                    _BOOK_ORDER.get(kv[0][0], 99),
                    _chapter_number(kv[0][1]),
                    kv[0][1],
                ),
            )
        ],
    }
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "facets": facets,
    }
