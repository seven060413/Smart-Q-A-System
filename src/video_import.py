"""视频候选导入与审核的共享逻辑。

供 scripts/collect_videos.py 与 scripts/review_videos.py 复用：
- 校验 bvid / node_key；
- upsert videos 与 video_candidates；
- 审核通过/拒绝时写 knowledge_point_videos。

本模块不做网络请求，也不自动提交事务；调用方负责 with conn / commit。
"""

from __future__ import annotations

import json
import re
import urllib.request

from .errors import ApiError
from .schema import _utcnow
from .videos import build_watch_url, normalize_node_keys

DEFAULT_COURSE_ID = "math"

_DURATION_RE = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})\s*$")


def video_id_for(bvid: str, page: int = 1) -> str:
    """视频主键：bilibili:BV...:1。"""
    page = max(1, int(page or 1))
    return f"bilibili:{bvid}:{page}"


def parse_duration(value) -> int | None:
    """把 480 / "8:00" / "1:02:03" 统一成秒。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    match = _DURATION_RE.match(text)
    if match is None:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def fetch_bilibili_meta(
    bvid: str, page: int = 1, timeout: float = 10.0
) -> dict:
    """离线调用 B 站公开 view 接口，解析 aid / 对应分 P 的 cid。

    只在采集/审核阶段使用，运行时绝不调用。接口不可用时抛 ValueError，
    由调用方决定跳过或提示人工填写 aid/cid。
    """
    bvid = (bvid or "").strip()
    build_watch_url(bvid, page)  # 校验 bvid
    page = max(1, int(page or 1))
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"无法获取 B 站视频信息: {exc}") from None

    if payload.get("code") != 0:
        raise ValueError(
            f"B 站接口返回 {payload.get('code')}: {payload.get('message')}"
        )

    data = payload.get("data") or {}
    pages = data.get("pages") or []
    cid = data.get("cid")
    for item in pages:
        if int(item.get("page") or 0) == page:
            cid = item.get("cid")
            break
    if cid is None and pages:
        cid = pages[0].get("cid")

    return {
        "bvid": data.get("bvid") or bvid,
        "aid": data.get("aid"),
        "cid": cid,
        "title": data.get("title"),
    }


def update_candidate_meta(conn, candidate_id: int, aid, cid) -> None:
    """把解析到的 aid/cid 写回候选，便于后续重审。"""
    conn.execute(
        "UPDATE video_candidates SET aid = ?, cid = ? WHERE id = ?",
        (aid, cid, candidate_id),
    )


def ensure_course(conn, course_id: str = DEFAULT_COURSE_ID) -> None:
    now = _utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO courses "
        "(id, code, name, subject, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (course_id, course_id, "小学数学", "math", now, now),
    )


def normalize_node_key(node_key: str) -> str:
    keys = normalize_node_keys([node_key])
    if not keys:
        raise ApiError(400, "INVALID_NODE_KEY", "知识点编号不能为空")
    return keys[0]


def node_name_for(
    conn, node_key: str, graph_version_id: str | None = None
) -> str | None:
    """取知识点名称；优先指定版本，否则取任意版本中的第一条。"""
    if graph_version_id:
        row = conn.execute(
            "SELECT name FROM graph_nodes "
            "WHERE graph_version_id = ? AND node_key = ?",
            (graph_version_id, node_key),
        ).fetchone()
        if row:
            return row["name"]
    row = conn.execute(
        "SELECT name FROM graph_nodes WHERE node_key = ? ORDER BY id LIMIT 1",
        (node_key,),
    ).fetchone()
    return row["name"] if row else None


def upsert_video(
    conn,
    *,
    bvid: str,
    page: int = 1,
    title: str,
    author: str | None = None,
    duration_seconds: int | None = None,
    cover_url: str | None = None,
    aid: int | None = None,
    cid: int | None = None,
    published_at: str | None = None,
    metadata: dict | None = None,
    course_id: str = DEFAULT_COURSE_ID,
    update_existing: bool = True,
) -> str:
    """写入/更新视频元数据，返回 video_id。bvid 非法时抛 ValueError。

    update_existing=False 时只保证视频行存在，不覆盖已有元数据；审核拒绝
    候选时使用，避免把已通过视频的标题/时长改掉。
    """
    bvid = (bvid or "").strip()
    watch_url = build_watch_url(bvid, page)  # 同时校验 bvid
    page = max(1, int(page or 1))
    video_id = video_id_for(bvid, page)
    now = _utcnow()
    ensure_course(conn, course_id)

    if update_existing:
        conflict_sql = (
            "ON CONFLICT(id) DO UPDATE SET "
            " aid = excluded.aid, cid = excluded.cid, "
            " title = excluded.title, author = excluded.author, "
            " duration_seconds = excluded.duration_seconds, "
            " cover_url = excluded.cover_url, watch_url = excluded.watch_url, "
            " published_at = excluded.published_at, "
            " metadata_json = excluded.metadata_json, updated_at = excluded.updated_at"
        )
    else:
        conflict_sql = "ON CONFLICT(id) DO NOTHING"

    conn.execute(
        "INSERT INTO videos "
        "(id, platform, bvid, page, aid, cid, title, author, duration_seconds, "
        " cover_url, watch_url, published_at, status, metadata_json, "
        " created_at, updated_at) "
        f"VALUES (?, 'bilibili', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?) "
        f"{conflict_sql}",
        (
            video_id,
            bvid,
            page,
            aid,
            cid,
            title or bvid,
            author,
            duration_seconds,
            cover_url,
            watch_url,
            published_at,
            json.dumps(metadata or {}, ensure_ascii=False),
            now,
            now,
        ),
    )
    return video_id


def upsert_candidate(
    conn,
    *,
    node_key: str,
    bvid: str,
    query: str,
    page: int = 1,
    title: str | None = None,
    author: str | None = None,
    duration_seconds: int | None = None,
    cover_url: str | None = None,
    aid: int | None = None,
    cid: int | None = None,
    play_count: int | None = None,
    published_at: str | None = None,
    search_rank: int | None = None,
    raw: dict | None = None,
    fetched_at: str | None = None,
    course_id: str = DEFAULT_COURSE_ID,
) -> int:
    """写入/更新采集候选，返回候选行 id。"""
    node_key = normalize_node_key(node_key)
    build_watch_url(bvid, page)  # 校验 bvid
    page = max(1, int(page or 1))
    now = fetched_at or _utcnow()
    ensure_course(conn, course_id)
    conn.execute(
        "INSERT INTO video_candidates "
        "(course_id, node_key, query, platform, bvid, page, aid, cid, title, author, "
        " duration_seconds, cover_url, play_count, published_at, search_rank, "
        " raw_json, fetched_at) "
        "VALUES (?, ?, ?, 'bilibili', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(course_id, node_key, query, platform, bvid, page) "
        "DO UPDATE SET "
        " aid = excluded.aid, cid = excluded.cid, "
        " title = excluded.title, author = excluded.author, "
        " duration_seconds = excluded.duration_seconds, "
        " cover_url = excluded.cover_url, play_count = excluded.play_count, "
        " published_at = excluded.published_at, "
        " search_rank = excluded.search_rank, raw_json = excluded.raw_json, "
        " fetched_at = excluded.fetched_at",
        (
            course_id,
            node_key,
            query,
            bvid,
            page,
            aid,
            cid,
            title,
            author,
            duration_seconds,
            cover_url,
            play_count,
            published_at,
            search_rank,
            json.dumps(raw or {}, ensure_ascii=False),
            now,
        ),
    )
    row = conn.execute(
        "SELECT id FROM video_candidates "
        "WHERE course_id = ? AND node_key = ? AND query = ? "
        "  AND platform = 'bilibili' AND bvid = ? AND page = ?",
        (course_id, node_key, query, bvid, page),
    ).fetchone()
    return row["id"]


def get_candidate(conn, candidate_id: int):
    return conn.execute(
        "SELECT * FROM video_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()


def upsert_mapping(
    conn,
    *,
    node_key: str,
    video_id: str,
    status: str,
    rank: int = 0,
    reviewer: str | None = None,
    note: str | None = None,
    source_graph_version_id: str | None = None,
    relation: str = "explains",
    course_id: str = DEFAULT_COURSE_ID,
) -> int:
    """写入/更新知识点-视频映射；approved/rejected 必须有 reviewer。"""
    if status not in ("pending", "approved", "rejected"):
        raise ValueError("invalid review status")
    if status != "pending" and not reviewer:
        raise ValueError("审核通过/拒绝时必须提供 reviewer")
    node_key = normalize_node_key(node_key)
    now = _utcnow()
    reviewed_at = now if status != "pending" else None
    reviewed_by = reviewer if status != "pending" else None
    ensure_course(conn, course_id)

    conn.execute(
        "INSERT INTO knowledge_point_videos "
        "(course_id, node_key, node_name, video_id, relation, rank, "
        " review_status, review_note, reviewed_by, reviewed_at, "
        " source_graph_version_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(course_id, node_key, video_id, relation) DO UPDATE SET "
        " node_name = excluded.node_name, rank = excluded.rank, "
        " review_status = excluded.review_status, "
        " review_note = excluded.review_note, "
        " reviewed_by = excluded.reviewed_by, "
        " reviewed_at = excluded.reviewed_at, "
        " source_graph_version_id = excluded.source_graph_version_id, "
        " updated_at = excluded.updated_at",
        (
            course_id,
            node_key,
            node_name_for(conn, node_key, source_graph_version_id),
            video_id,
            relation,
            rank,
            status,
            note,
            reviewed_by,
            reviewed_at,
            source_graph_version_id,
            now,
            now,
        ),
    )
    row = conn.execute(
        "SELECT id FROM knowledge_point_videos "
        "WHERE course_id = ? AND node_key = ? AND video_id = ? AND relation = ?",
        (course_id, node_key, video_id, relation),
    ).fetchone()
    return row["id"]


def approve_candidate(
    conn,
    candidate_id: int,
    *,
    reviewer: str,
    rank: int = 0,
    note: str | None = None,
    source_graph_version_id: str | None = None,
    course_id: str = DEFAULT_COURSE_ID,
    fetch_meta: bool = False,
) -> dict:
    """把候选标记为审核通过：upsert 视频 + 映射 approved。

    fetch_meta=True 时调用 B 站公开 view 接口补齐 aid/cid，用于官方嵌入
    播放器；该调用只发生在审核阶段，运行时不会访问 B 站。
    """
    row = get_candidate(conn, candidate_id)
    if row is None:
        raise ValueError(f"候选 {candidate_id} 不存在")

    aid, cid = row["aid"], row["cid"]
    if fetch_meta and (not aid or not cid):
        meta = fetch_bilibili_meta(row["bvid"], row["page"])
        aid, cid = meta.get("aid"), meta.get("cid")
        update_candidate_meta(conn, candidate_id, aid, cid)

    video_id = upsert_video(
        conn,
        bvid=row["bvid"],
        page=row["page"],
        title=row["title"] or row["bvid"],
        author=row["author"],
        duration_seconds=row["duration_seconds"],
        cover_url=row["cover_url"],
        aid=aid,
        cid=cid,
        published_at=row["published_at"],
        metadata={"candidate_id": candidate_id, "query": row["query"]},
        course_id=course_id,
    )
    mapping_id = upsert_mapping(
        conn,
        node_key=row["node_key"],
        video_id=video_id,
        status="approved",
        rank=rank,
        reviewer=reviewer,
        note=note,
        source_graph_version_id=source_graph_version_id,
        course_id=course_id,
    )
    return {
        "candidate_id": candidate_id,
        "mapping_id": mapping_id,
        "video_id": video_id,
        "node_key": row["node_key"],
        "bvid": row["bvid"],
        "aid": aid,
        "cid": cid,
    }


def reject_candidate(
    conn,
    candidate_id: int,
    *,
    reviewer: str,
    note: str | None = None,
    source_graph_version_id: str | None = None,
    course_id: str = DEFAULT_COURSE_ID,
) -> dict:
    """把候选标记为审核拒绝；保留记录，不物理删除。"""
    row = get_candidate(conn, candidate_id)
    if row is None:
        raise ValueError(f"候选 {candidate_id} 不存在")
    video_id = upsert_video(
        conn,
        bvid=row["bvid"],
        page=row["page"],
        title=row["title"] or row["bvid"],
        author=row["author"],
        duration_seconds=row["duration_seconds"],
        cover_url=row["cover_url"],
        aid=row["aid"],
        cid=row["cid"],
        published_at=row["published_at"],
        metadata={"candidate_id": candidate_id, "query": row["query"]},
        course_id=course_id,
        update_existing=False,
    )
    mapping_id = upsert_mapping(
        conn,
        node_key=row["node_key"],
        video_id=video_id,
        status="rejected",
        reviewer=reviewer,
        note=note,
        source_graph_version_id=source_graph_version_id,
        course_id=course_id,
    )
    return {
        "candidate_id": candidate_id,
        "mapping_id": mapping_id,
        "video_id": video_id,
        "node_key": row["node_key"],
        "bvid": row["bvid"],
    }
