"""个性化推荐：今日建议。

设计原则（与产品口径一致）：
- 内容优先：错题、学情趋势、聊天知识点共同决定候选，年级不参与候选过滤；
- 年级只做软权重：同年级优先、低年级前置优先补、高年级内容只在内容信号强时出现；
- 可解释：每条建议都带 reason，前端直接展示；
- 只读：本模块不写数据库，所有统计都基于已有学习数据。

打分是规则加权，不依赖外部模型；后续可以替换权重或接入排序模型，接口保持不变。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Dict, List

import networkx as nx

from . import quiz_service
from .subgraph import RAW_PATH
from .videos import get_videos_for_nodes

# 近 14 天的错题会额外加权；聊天窗口放宽到 90 天，捕捉持续关注的主题。
RECENT_DAYS = 14
CHAT_WINDOW_DAYS = 90
HALF_LIFE_DAYS = 21.0
MAX_PREREQUISITES = 12
MIN_SCORE = 0.12
DEFAULT_LIMIT = 3

KIND_BADGES = {
    "wrong": "错题巩固",
    "trend": "趋势提醒",
    "chat": "聊天关注",
    "prerequisite": "补前置",
    "onboarding": "开始",
}

GRADE_LABELS = {
    1: "一年级",
    2: "二年级",
    3: "三年级",
    4: "四年级",
    5: "五年级",
    6: "六年级",
    7: "七年级",
    8: "八年级",
    9: "九年级",
}


def _iso_days_ago(days: int) -> str:
    value = datetime.now(timezone.utc) - timedelta(days=days)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _decay(value: str | None) -> float:
    """时间衰减：半衰期 21 天；没有时间戳时给 0.4 的基础分。"""
    parsed = _parse_ts(value)
    if parsed is None:
        return 0.4
    days = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400)
    return 0.5 ** (days / HALF_LIFE_DAYS)


def _grade_label(grade: int | None) -> str:
    return GRADE_LABELS.get(grade, "")


def _candidate(
    candidates: Dict[str, Dict[str, Any]], key: str, dataset
) -> Dict[str, Any]:
    if key not in candidates:
        topic = dataset.topics.get(key) or {}
        candidates[key] = {
            "node_key": key,
            "name": topic.get("name") or key,
            "grade": topic.get("grade"),
            "chapter": topic.get("chapter_label") or topic.get("chapter") or "",
            "wrong_count": 0,
            "recent_wrong": 0,
            "last_wrong_at": None,
            "chat_asks": 0,
            "last_chat_at": None,
            "trend_weak_count": 0,
            "repeated_wrong_count": 0,
            "improved": False,
            "prereq_for": None,
            "prereq_boost": 0.0,
            "inherited_last_at": None,
            # 聊天图谱与诊断图谱是两套 ID；无法按名称映射时只能提供问 AI/看视频。
            "chat_only": False,
        }
    return candidates[key]


@lru_cache(maxsize=1)
def _chat_node_names() -> Dict[str, str]:
    """聊天图谱（data/raw/math.json）的 ID→名称，作为消息快照名称的兜底。"""
    try:
        data = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return {
        node["id"]: node.get("name") or ""
        for node in data.get("nodes") or []
        if node.get("id")
    }


_CHAT_GRADE_RE = re.compile(r"^math_(\d)[ab]_", re.IGNORECASE)


def _chat_grade_from_key(key: str | None) -> int | None:
    """从 math_5b_rjb_cpt22 这类 ID 解析年级；失败返回 None。"""
    match = _CHAT_GRADE_RE.match(key or "")
    if not match:
        return None
    grade = int(match.group(1))
    return grade if 1 <= grade <= 9 else None


def _normalize_name(name: str | None) -> str:
    """去掉空白和常见标点，降低两套图谱命名差异带来的漏匹配。"""
    return re.sub(r"[\s（）()【】\[\]·、，,。.]", "", name or "")


def _name_index(dataset) -> Dict[str, List[tuple[str, int | None]]]:
    index: Dict[str, List[tuple[str, int | None]]] = {}
    for key, topic in dataset.topics.items():
        normalized = _normalize_name(topic.get("name"))
        if normalized:
            index.setdefault(normalized, []).append((key, topic.get("grade")))
    return index


def _match_pansgo(
    index: Dict[str, List[tuple[str, int | None]]],
    name: str | None,
    grade: int | None,
) -> str | None:
    """把聊天图谱的知识点按名称映射到 pansgo 节点；同名时优先同年级。"""
    options = index.get(_normalize_name(name)) or []
    if not options:
        return None
    for key, option_grade in options:
        if grade is not None and option_grade == grade:
            return key
    return options[0][0]


def _wrong_signals(conn, user_id: str, recent_cutoff: str) -> List[Any]:
    """按知识点聚合未掌握错题；已标记掌握/忽略的题不再计入。"""
    return conn.execute(
        """
        SELECT a.node_key,
               COUNT(*) AS wrong_count,
               SUM(CASE WHEN a.created_at >= ? THEN 1 ELSE 0 END) AS recent_wrong,
               MAX(a.created_at) AS last_wrong_at,
               MAX(a.topic_name) AS topic_name,
               MAX(a.grade) AS grade,
               MAX(a.chapter) AS chapter
        FROM quiz_attempts a
        JOIN quiz_sessions s ON s.id = a.session_id
        LEFT JOIN wrong_question_marks w
          ON w.user_id = s.user_id
         AND w.dataset_version = a.dataset_version
         AND w.question_id = a.question_id
        WHERE s.user_id = ?
          AND a.is_correct = 0
          AND a.node_key IS NOT NULL
          AND (w.status IS NULL OR w.status = 'open')
        GROUP BY a.node_key
        """,
        (recent_cutoff, user_id),
    ).fetchall()


def _chat_signals(conn, user_id: str, cutoff: str) -> List[Any]:
    """聊天里反复出现的本体知识点；只取成功回答，避免失败请求污染。"""
    return conn.execute(
        """
        SELECT mkp.node_key, MAX(mkp.node_name) AS node_name,
               COUNT(*) AS asks, MAX(m.created_at) AS last_ask
        FROM message_knowledge_points mkp
        JOIN messages m ON m.id = mkp.message_id
        JOIN conversations c ON c.id = m.conversation_id
        WHERE c.user_id = ? AND c.deleted_at IS NULL
          AND m.role = 'assistant' AND m.status = 'completed'
          AND mkp.relation = 'body'
          AND m.created_at >= ?
        GROUP BY mkp.node_key
        """,
        (user_id, cutoff),
    ).fetchall()


def _trend_signals(conn, user_id: str):
    """复用学情趋势，拿到持续薄弱、反复错和已掌握集合。"""
    trends = quiz_service.build_trends(conn, user_id, limit=12)
    mastered: set[str] = set()
    last_at: Dict[str, str] = {}
    for point in trends.get("points") or []:
        history = point.get("history") or []
        if not history:
            continue
        latest = history[-1]
        last_at[point["node_key"]] = latest.get("created_at")
        if latest.get("status") in ("mastered", "proficient"):
            mastered.add(point["node_key"])
    return trends, mastered, last_at


def _collect(conn, user_id: str, dataset):
    candidates: Dict[str, Dict[str, Any]] = {}
    recent_cutoff = _iso_days_ago(RECENT_DAYS)
    chat_cutoff = _iso_days_ago(CHAT_WINDOW_DAYS)

    for row in _wrong_signals(conn, user_id, recent_cutoff):
        item = _candidate(candidates, row["node_key"], dataset)
        item["wrong_count"] = int(row["wrong_count"] or 0)
        item["recent_wrong"] = int(row["recent_wrong"] or 0)
        item["last_wrong_at"] = row["last_wrong_at"]
        # 老作答的快照可能为空，用数据集补齐展示字段。
        if row["topic_name"]:
            item["name"] = row["topic_name"]
        if row["grade"] is not None:
            item["grade"] = row["grade"]
        if row["chapter"]:
            item["chapter"] = row["chapter"]

    trends, mastered, trend_last_at = _trend_signals(conn, user_id)
    for row in trends.get("continuous_weak") or []:
        key = row.get("node_key")
        if not key:
            continue
        item = _candidate(candidates, key, dataset)
        item["trend_weak_count"] = int(row.get("count") or 0)
        item["name"] = row.get("name") or item["name"]
        item["inherited_last_at"] = trend_last_at.get(key)
    for row in trends.get("repeated_wrong") or []:
        key = row.get("node_key")
        if not key:
            continue
        item = _candidate(candidates, key, dataset)
        item["repeated_wrong_count"] = int(row.get("wrong_count") or 0)
        item["name"] = row.get("name") or item["name"]
        item["inherited_last_at"] = item["inherited_last_at"] or trend_last_at.get(key)
    for row in trends.get("improved") or []:
        key = row.get("node_key")
        if key in candidates:
            candidates[key]["improved"] = True

    name_index = _name_index(dataset)
    chat_names = _chat_node_names()
    for row in _chat_signals(conn, user_id, chat_cutoff):
        raw_key = row["node_key"]
        if not raw_key:
            continue
        raw_name = (row["node_name"] or "").strip()
        # 少数旧消息的 node_name 为空或只有编号，用聊天图谱自身补名称。
        if not raw_name or raw_name == raw_key or raw_name.isdigit():
            raw_name = (chat_names.get(raw_key) or raw_name).strip()
        chat_grade = _chat_grade_from_key(raw_key)
        mapped_key = _match_pansgo(name_index, raw_name, chat_grade)
        key = mapped_key or raw_key
        item = _candidate(candidates, key, dataset)
        if mapped_key is None:
            # 跨图谱无法映射：保留聊天图谱的 ID/名称/年级，只提供问 AI/看视频。
            item["chat_only"] = True
            if raw_name:
                item["name"] = raw_name
            if chat_grade is not None:
                item["grade"] = chat_grade
        item["chat_asks"] += int(row["asks"] or 0)
        item["last_chat_at"] = max(
            filter(None, [item["last_chat_at"], row["last_ask"]]), default=None
        )

    # 为薄弱点补一层直接前置：低年级前置往往比继续刷当前年级更有效。
    weak_children = [
        item
        for item in candidates.values()
        if item["wrong_count"] or item["trend_weak_count"] or item["repeated_wrong_count"]
    ]
    weak_children.sort(
        key=lambda item: (
            -item["wrong_count"],
            -item["trend_weak_count"],
            -item["repeated_wrong_count"],
        )
    )
    added = 0
    for child in weak_children:
        if child["node_key"] not in dataset.graph:
            continue
        for pred in dataset.graph.predecessors(child["node_key"]):
            if added >= MAX_PREREQUISITES:
                break
            if pred in mastered or pred not in dataset.topics:
                continue
            item = _candidate(candidates, pred, dataset)
            if item["prereq_for"] is None:
                item["prereq_for"] = child["node_key"]
            item["prereq_boost"] = 1.0
            item["inherited_last_at"] = (
                item["inherited_last_at"]
                or child.get("last_wrong_at")
                or trend_last_at.get(child["node_key"])
            )
            added += 1

    return candidates, mastered, trends


def _grade_fit(grade: int | None, user_grade: int | None, is_current_prereq: bool) -> float:
    if user_grade is None or grade is None:
        return 0.5
    if grade == user_grade:
        return 1.0
    if grade < user_grade:
        return 0.9 if is_current_prereq else 0.6
    # 高年级内容不隐藏，但默认排在后面；只有内容信号足够强时才会进榜。
    return 0.3


def _score(item, user_grade, current_prereqs) -> float:
    wrong_score = (
        min(1.0, item["wrong_count"] / 3.0) * 0.7
        + min(1.0, item["recent_wrong"] / 2.0) * 0.3
    )
    trend_score = (
        min(1.0, item["trend_weak_count"] / 3.0) * 0.7
        + min(1.0, item["repeated_wrong_count"] / 3.0) * 0.3
    )
    if item["improved"]:
        trend_score *= 0.4
    chat_score = min(1.0, item["chat_asks"] / 3.0)
    prereq_score = 1.0 if item["prereq_boost"] else 0.0
    fit = _grade_fit(
        item["grade"], user_grade, item["node_key"] in current_prereqs
    )
    last_at = max(
        filter(
            None,
            [
                item["last_wrong_at"],
                item["last_chat_at"],
                item["inherited_last_at"],
            ],
        ),
        default=None,
    )
    recency = _decay(last_at)
    return round(
        0.40 * wrong_score
        + 0.15 * trend_score
        + 0.15 * recency
        + 0.10 * chat_score
        + 0.10 * prereq_score
        + 0.10 * fit,
        4,
    )


def _has_signal(item) -> bool:
    return bool(
        item["wrong_count"]
        or item["recent_wrong"]
        or item["trend_weak_count"]
        or item["repeated_wrong_count"]
        or item["chat_asks"]
        or item["prereq_boost"]
    )


def _kind(item) -> str:
    if item["wrong_count"] or item["repeated_wrong_count"]:
        return "wrong"
    if item["trend_weak_count"]:
        return "trend"
    if item["chat_asks"]:
        return "chat"
    return "prerequisite"


def _reason(item, candidates) -> str:
    evidence: List[str] = []
    if item["wrong_count"]:
        text = f"「{item['name']}」错过 {item['wrong_count']} 次"
        if item["recent_wrong"]:
            text += f"，最近 {RECENT_DAYS} 天又错 {item['recent_wrong']} 次"
        evidence.append(text)
    if item["trend_weak_count"] >= 2:
        evidence.append(f"最近 {item['trend_weak_count']} 次诊断都显示薄弱")
    elif item["repeated_wrong_count"] >= 2:
        evidence.append(f"同类题反复错 {item['repeated_wrong_count']} 次")
    if item["chat_asks"]:
        evidence.append(f"最近在聊天里问过 {item['chat_asks']} 次")
    if item["prereq_for"] and not (
        item["wrong_count"]
        or item["trend_weak_count"]
        or item["repeated_wrong_count"]
        or item["chat_asks"]
    ):
        child = candidates.get(item["prereq_for"]) or {}
        child_name = child.get("name") or item["prereq_for"]
        evidence.append(f"它是「{child_name}」的前置，先补会更稳")
    return "；".join(evidence[:2]) or "根据最近的学习记录推荐"


def _video_payload(video: dict) -> dict:
    return {
        "bvid": video.get("bvid") or "",
        "aid": video.get("aid"),
        "cid": video.get("cid"),
        "page": video.get("page") or 1,
        "title": video.get("title") or "",
        "cover_url": video.get("cover_url") or "",
        "duration_seconds": video.get("duration_seconds"),
    }


def _actions(item, kind: str, video: dict | None) -> List[dict]:
    diagnose = {
        "type": "diagnose",
        "label": "去巩固" if kind in ("wrong", "trend") else "去诊断",
        "node_key": item["node_key"],
        "mode": "single",
    }
    chat = {
        "type": "chat",
        "label": "问 AI",
        "node_key": item["node_key"],
        "question": f"帮我讲讲「{item['name']}」，从我最薄弱的地方开始。",
    }
    video_action = None
    if video:
        video_action = {
            "type": "video",
            "label": "看视频",
            "node_key": item["node_key"],
            "video": _video_payload(video),
        }
    if item.get("chat_only"):
        # 诊断图谱没有这个节点 ID，不能提供「去诊断」，否则会跳到空页面。
        ordered = [chat]
        if video_action:
            ordered.append(video_action)
        return ordered
    if kind == "chat":
        ordered = [chat, diagnose]
    else:
        ordered = [diagnose]
    if video_action:
        ordered.append(video_action)
    if kind != "chat":
        ordered.append(chat)
    return ordered


def _fallback_item(conn, user_id: str, user_grade: int | None) -> dict:
    """没有足够信号时给一个可执行的起点，而不是空白卡片。"""
    has_session = conn.execute(
        "SELECT 1 FROM quiz_sessions "
        "WHERE user_id = ? AND status = 'completed' LIMIT 1",
        (user_id,),
    ).fetchone()
    label = _grade_label(user_grade)
    if has_session:
        name = "再做一次诊断"
        reason = "最近没有明显的薄弱信号；再做一次诊断可以比较这次的变化。"
    else:
        name = "先做一次诊断"
        prefix = f"完成一次{label}诊断" if label else "完成一次诊断"
        reason = f"{prefix}后，我会根据你的薄弱点、趋势和聊天记录给出建议。"
    return {
        "node_key": "",
        "name": name,
        "grade": user_grade,
        "chapter": "",
        "kind": "onboarding",
        "badge": KIND_BADGES["onboarding"],
        "score": 0.0,
        "reason": reason,
        "actions": [
            {
                "type": "diagnose",
                "label": "去诊断",
                "mode": "grade" if user_grade else "single",
            }
        ],
    }


def today(
    conn,
    user_id: str,
    *,
    grade: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """生成今日建议；返回 items（最多 limit 条）与生成原因。"""
    dataset = quiz_service.load_dataset()
    candidates, _mastered, _trends = _collect(conn, user_id, dataset)

    current_weak = {
        item["node_key"]
        for item in candidates.values()
        if item["grade"] == grade
        and (
            item["wrong_count"]
            or item["trend_weak_count"]
            or item["repeated_wrong_count"]
        )
    }
    current_prereqs: set[str] = set()
    for key in current_weak:
        if key in dataset.graph:
            current_prereqs |= set(nx.ancestors(dataset.graph, key))

    scored = []
    for item in candidates.values():
        if not _has_signal(item):
            continue
        score = _score(item, grade, current_prereqs)
        if score >= MIN_SCORE:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))

    top = scored[: max(1, min(limit, 10))]
    video_map: Dict[str, dict] = {}
    if top:
        video_data = get_videos_for_nodes(
            conn, [item["node_key"] for _, item in top], limit=1
        )
        for entry in video_data.get("items") or []:
            videos = entry.get("videos") or []
            if videos:
                video_map[entry["node_key"]] = videos[0]

    items = []
    for score, item in top:
        kind = _kind(item)
        items.append(
            {
                "node_key": item["node_key"],
                "name": item["name"],
                "grade": item["grade"],
                "chapter": item["chapter"],
                "kind": kind,
                "badge": KIND_BADGES.get(kind, ""),
                "score": score,
                "reason": _reason(item, candidates),
                "actions": _actions(item, kind, video_map.get(item["node_key"])),
            }
        )

    if not items:
        items = [_fallback_item(conn, user_id, grade)]

    return {
        "grade": grade,
        "generated_at": _iso_now(),
        "window_days": CHAT_WINDOW_DAYS,
        "items": items,
        "reason": None if scored else "no_data",
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
