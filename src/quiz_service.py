"""学情诊断服务：数据集加载、题库读取、会话创建与作答。

数据来源：
- data/processed/pansgo_math_k12.json            图谱（870 个知识点、1,459 条先修边）
- data/processed/pansgo_math_k12_questions.json  题库（3,627 题）
- data/processed/pansgo_math_k12_catalog.json    章节目录

运行时答案只从数据库读取，接口绝不返回 answer。
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List

import networkx as nx

from . import pansgo
from .errors import ApiError
from .question_bank import Question, question_from_dict
from .quiz_engine import QuizEngine, QuizStateError
from .security import now_utc

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / "data" / "processed" / "pansgo_math_k12.json"
QUESTIONS_PATH = ROOT / "data" / "processed" / "pansgo_math_k12_questions.json"
CATALOG_PATH = ROOT / "data" / "processed" / "pansgo_math_k12_catalog.json"

SESSION_TTL_HOURS = 24
MAX_SCOPE_NODES = 500
DEFAULT_MAX_QUESTIONS = {"single": 16, "chapter": 16, "grade": 40}
DEFAULT_MASTERY = {"single": 3, "chapter": 3, "grade": 2}
MAX_QUESTIONS_RANGE = {"single": (8, 30), "chapter": (8, 30), "grade": (20, 60)}


@dataclass(frozen=True)
class Dataset:
    version: str
    topics: Dict[str, Dict[str, Any]]
    graph: nx.DiGraph
    catalog: Dict[str, Any]


def _dataset_version(data: Dict[str, Any]) -> str:
    metadata = data.get("metadata") or {}
    return str(metadata.get("source_commit") or pansgo.SOURCE_COMMIT)


@lru_cache(maxsize=1)
def load_dataset() -> Dataset:
    """加载并缓存图谱与目录；文件缺失时返回明确错误。"""
    try:
        graph_data = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ApiError(
            503,
            "DATASET_UNAVAILABLE",
            "诊断图谱未生成，请先运行 scripts/fetch_pansgo.py 和 scripts/build_pansgo_graph.py",
        ) from None

    topics: Dict[str, Dict[str, Any]] = {}
    graph = nx.DiGraph()
    for node in graph_data.get("nodes", []):
        props = node.get("properties") or {}
        topic = {
            "id": node["id"],
            "name": node.get("name") or node["id"],
            "grade": props.get("grade"),
            "semester": props.get("semester"),
            "book": props.get("book"),
            "chapter": props.get("chapter"),
            "chapter_label": props.get("chapter_label"),
        }
        topics[topic["id"]] = topic
        graph.add_node(topic["id"])

    for edge in graph_data.get("edges", []):
        if edge.get("type") != "prerequisites_for":
            continue
        source, target = edge.get("source"), edge.get("target")
        if source in topics and target in topics:
            props = edge.get("properties") or {}
            graph.add_edge(
                source,
                target,
                strength=str(props.get("strength") or "hard"),
            )

    try:
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8")).get(
            "questions", []
        )
        catalog = pansgo.build_catalog(list(topics.values()), questions)

    return Dataset(
        version=_dataset_version(graph_data),
        topics=topics,
        graph=graph,
        catalog=catalog,
    )


def reset_dataset_cache() -> None:
    """测试用：清空数据集缓存。"""
    load_dataset.cache_clear()


def get_catalog() -> Dict[str, Any]:
    dataset = load_dataset()
    return {
        **dataset.catalog,
        "dataset_version": dataset.version,
        "quality_note": "题目与知识点由 AI 生成、未经一线教师审核，仅用于薄弱点筛查。",
        "license": pansgo.LICENSE,
    }


class DBQuestionProvider:
    """按知识点从 questions 表读取题目，并在一次请求内缓存。"""

    def __init__(self, conn, dataset_version: str):
        self.conn = conn
        self.dataset_version = dataset_version
        self._cache: Dict[str, List[Question]] = {}

    def __call__(self, node_id: str) -> List[Question]:
        if node_id in self._cache:
            return self._cache[node_id]
        try:
            rows = self.conn.execute(
                "SELECT id, node_key, difficulty, type, prompt, choices_json, answer, "
                "explanation, figure_svg, verify_expr, hide_choice_text, "
                "accept_json, unordered "
                "FROM questions WHERE dataset_version = ? AND node_key = ? ORDER BY id",
                (self.dataset_version, node_id),
            ).fetchall()
        except Exception:
            raise ApiError(
                503,
                "QUESTION_BANK_UNAVAILABLE",
                "题库未初始化，请先运行 scripts/seed_pansgo_questions.py",
            ) from None

        questions = []
        for row in rows:
            choices = json.loads(row["choices_json"]) if row["choices_json"] else []
            questions.append(
                question_from_dict(
                    {
                        "id": row["id"],
                        "topicId": row["node_key"],
                        "difficulty": row["difficulty"],
                        "type": row["type"],
                        "prompt": row["prompt"],
                        "choices": choices,
                        "answer": row["answer"],
                        "explanation": row["explanation"] or "",
                        "figure": row["figure_svg"] or "",
                        "verify": row["verify_expr"] or "",
                        "hideChoiceText": bool(row["hide_choice_text"]),
                        "accept": json.loads(row["accept_json"]) if row["accept_json"] else [],
                        "unordered": bool(row["unordered"]),
                    }
                )
            )
        self._cache[node_id] = questions
        return questions


def ensure_question_bank(conn, dataset_version: str) -> None:
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM questions WHERE dataset_version = ?",
            (dataset_version,),
        ).fetchone()["c"]
    except Exception:
        raise ApiError(
            503,
            "QUESTION_BANK_UNAVAILABLE",
            "题库未初始化，请先运行 scripts/seed_pansgo_questions.py",
        ) from None
    if count == 0:
        raise ApiError(
            503,
            "QUESTION_BANK_EMPTY",
            "题库为空，请先运行 scripts/seed_pansgo_questions.py",
        )


def seed_questions(conn, questions: Iterable[Dict[str, Any]], dataset_version: str) -> int:
    """幂等写入题库；返回写入条数。"""
    now = now_utc()
    rows = []
    for q in questions:
        rows.append(
            (
                dataset_version,
                q.get("id"),
                q.get("topicId"),
                None,
                None,
                None,
                q.get("difficulty") or "basic",
                q.get("type") or "choice",
                q.get("prompt") or "",
                json.dumps(q.get("choices") or [], ensure_ascii=False),
                str(q.get("answer", "")),
                q.get("explanation") or "",
                q.get("figure") or "",
                q.get("verify") or "",
                1 if q.get("hideChoiceText") else 0,
                json.dumps(q.get("accept") or [], ensure_ascii=False),
                1 if q.get("unordered") else 0,
                now,
                now,
            )
        )
    conn.executemany(
        "INSERT INTO questions "
        "(dataset_version, id, node_key, node_name, grade, chapter, difficulty, type, "
        " prompt, choices_json, answer, explanation, figure_svg, verify_expr, "
        " hide_choice_text, accept_json, unordered, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(dataset_version, id) DO UPDATE SET "
        " node_key=excluded.node_key, difficulty=excluded.difficulty, type=excluded.type, "
        " prompt=excluded.prompt, choices_json=excluded.choices_json, answer=excluded.answer, "
        " explanation=excluded.explanation, figure_svg=excluded.figure_svg, "
        " verify_expr=excluded.verify_expr, hide_choice_text=excluded.hide_choice_text, "
        " accept_json=excluded.accept_json, unordered=excluded.unordered, "
        " updated_at=excluded.updated_at",
        rows,
    )
    conn.commit()
    return len(rows)


# ---------- 会话 ----------


def create_session(conn, auth_ctx, payload: Dict[str, Any]) -> Dict[str, Any]:
    dataset = load_dataset()
    ensure_question_bank(conn, dataset.version)

    mode = str(payload.get("mode") or "single")
    if mode not in pansgo_mode_names():
        raise ApiError(400, "INVALID_MODE", "诊断模式只能是 single / chapter / grade")

    node_ids, grade, semester = _resolve_scope(dataset, mode, payload)
    max_questions = _param(
        payload, "max_questions", DEFAULT_MAX_QUESTIONS[mode], MAX_QUESTIONS_RANGE[mode]
    )
    mastery_raw = payload.get("mastery_streak")
    try:
        mastery = (
            int(mastery_raw) if mastery_raw is not None else DEFAULT_MASTERY[mode]
        )
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_MASTERY", "掌握标准只能是 2 / 3 / 5") from None
    if mastery not in (2, 3, 5):
        raise ApiError(400, "INVALID_MASTERY", "掌握标准只能是 2 / 3 / 5")

    provider = DBQuestionProvider(conn, dataset.version)
    try:
        engine = QuizEngine.start(
            dataset.topics,
            dataset.graph,
            provider,
            mode=mode,
            node_ids=node_ids,
            max_questions=max_questions,
            mastery_streak=mastery,
        )
    except ValueError as exc:
        raise ApiError(400, "INVALID_SCOPE", str(exc)) from None

    session_id = "qs_" + secrets.token_hex(16)
    now = _utcnow()
    # 顺手清理过期的游客会话，避免匿名数据无限增长。
    conn.execute(
        "DELETE FROM quiz_sessions WHERE user_id IS NULL AND expires_at < ?", (now,)
    )
    expires = _iso(datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS))
    finished = bool(engine.state["finished"])
    result = engine.result() if finished else None

    conn.execute(
        "INSERT INTO quiz_sessions "
        "(id, user_id, mode, grade, semester, scope_json, max_questions, mastery_streak, "
        " status, state_json, result_json, created_at, updated_at, finished_at, expires_at, "
        " dataset_version, scope_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            auth_ctx.user["id"] if auth_ctx else None,
            mode,
            grade,
            semester,
            json.dumps({"node_ids": node_ids}, ensure_ascii=False),
            max_questions,
            mastery,
            "completed" if finished else "active",
            json.dumps(engine.state, ensure_ascii=False),
            json.dumps(result, ensure_ascii=False) if result else None,
            now,
            now,
            now if finished else None,
            expires,
            dataset.version,
            len(node_ids),
        ),
    )
    conn.commit()

    return _session_payload(session_id, engine, result)


def backfill_grade_snapshots(conn) -> int:
    """为历史数据补齐年级快照（幂等），返回本次补齐的会话数。

    - quiz_sessions.grade 为 NULL：从 scope_json 的 node_ids 反推；只有这些
      知识点同属一个年级时才写入，跨年级混合范围保持 NULL。
    - quiz_attempts.grade 为 NULL：用同版本题库的 questions.grade 回填。

    旧版本只在「整年级摸底」时写 grade，单点/章节会话都是 NULL；不补齐的话，
    前端按学生年级查看趋势时会把历史数据整批过滤掉。
    """
    dataset = load_dataset()
    updated_sessions = 0
    rows = conn.execute(
        "SELECT id, scope_json FROM quiz_sessions WHERE grade IS NULL"
    ).fetchall()
    with conn:
        for row in rows:
            try:
                node_ids = json.loads(row["scope_json"]).get("node_ids") or []
            except (TypeError, ValueError, AttributeError):
                continue
            grades = {
                dataset.topics.get(str(node_id), {}).get("grade")
                for node_id in node_ids
            }
            grades.discard(None)
            if len(grades) == 1:
                conn.execute(
                    "UPDATE quiz_sessions SET grade = ? WHERE id = ?",
                    (grades.pop(), row["id"]),
                )
                updated_sessions += 1
        conn.execute(
            "UPDATE quiz_attempts SET grade = ("
            "  SELECT q.grade FROM questions q "
            "  WHERE q.dataset_version = quiz_attempts.dataset_version "
            "    AND q.id = quiz_attempts.question_id"
            ") WHERE grade IS NULL"
        )
        # 更早的作答没有 dataset_version，按 node_key 从当前数据集补。
        missing_attempts = conn.execute(
            "SELECT id, node_key FROM quiz_attempts WHERE grade IS NULL"
        ).fetchall()
        attempt_updates = []
        for row in missing_attempts:
            grade = dataset.topics.get(str(row["node_key"]), {}).get("grade")
            if grade is not None:
                attempt_updates.append((grade, row["id"]))
        if attempt_updates:
            conn.executemany(
                "UPDATE quiz_attempts SET grade = ? WHERE id = ?", attempt_updates
            )
    return updated_sessions


def answer_session(conn, auth_ctx, payload: Dict[str, Any]) -> Dict[str, Any]:
    dataset = load_dataset()
    session = _load_session(conn, payload.get("session_id"))
    _check_owner(session, auth_ctx)
    _check_active(session)

    client_request_id = payload.get("client_request_id")
    if client_request_id:
        existing = conn.execute(
            "SELECT response_json FROM quiz_attempts "
            "WHERE session_id = ? AND client_request_id = ?",
            (session["id"], client_request_id),
        ).fetchone()
        if existing is not None and existing["response_json"]:
            return json.loads(existing["response_json"])

    provider = DBQuestionProvider(conn, dataset.version)
    engine = QuizEngine.resume(
        dataset.topics,
        dataset.graph,
        provider,
        json.loads(session["state_json"]),
    )
    answered_node = engine.state.get("current_node")
    question_id = str(payload.get("question_id") or "")
    raw_answer = payload.get("answer")

    # 作答前的题目内容：写入 attempts 快照，题库后续更新不影响错题集。
    question = _find_question(provider, answered_node, question_id)
    try:
        result = engine.answer(question_id, "" if raw_answer is None else str(raw_answer))
    except QuizStateError as exc:
        raise ApiError(409, "QUIZ_STATE", str(exc)) from None

    response = {"session_id": session["id"], **result}
    response_json = json.dumps(response, ensure_ascii=False)
    finished = bool(engine.state["finished"])
    now = _utcnow()
    snapshot = _attempt_snapshot(dataset, answered_node, question)

    try:
        conn.execute(
            "INSERT INTO quiz_attempts "
            "(session_id, question_id, node_key, ordinal, student_answer, is_correct, "
            " client_request_id, response_json, created_at, dataset_version, difficulty, "
            " topic_name, chapter, grade, prompt_snapshot, choices_snapshot_json, "
            " answer_snapshot, explanation_snapshot, figure_snapshot) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session["id"],
                question_id,
                answered_node,
                engine.state["answered"],
                "" if raw_answer is None else str(raw_answer),
                1 if result["is_correct"] else 0,
                client_request_id,
                response_json,
                now,
                snapshot["dataset_version"],
                snapshot["difficulty"],
                snapshot["topic_name"],
                snapshot["chapter"],
                snapshot["grade"],
                snapshot["prompt"],
                snapshot["choices_json"],
                snapshot["answer"],
                snapshot["explanation"],
                snapshot["figure"],
            ),
        )
        conn.execute(
            "UPDATE quiz_sessions SET state_json = ?, status = ?, result_json = ?, "
            "updated_at = ?, finished_at = ? WHERE id = ?",
            (
                json.dumps(engine.state, ensure_ascii=False),
                "completed" if finished else "active",
                json.dumps(result["result"], ensure_ascii=False) if finished else None,
                now,
                now if finished else None,
                session["id"],
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        if client_request_id:
            existing = conn.execute(
                "SELECT response_json FROM quiz_attempts "
                "WHERE session_id = ? AND client_request_id = ?",
                (session["id"], client_request_id),
            ).fetchone()
            if existing is not None and existing["response_json"]:
                return json.loads(existing["response_json"])
        raise ApiError(409, "ALREADY_ANSWERED", "这道题已经提交过了") from None

    return response


def abort_session(conn, auth_ctx, payload: Dict[str, Any]) -> Dict[str, Any]:
    session = _load_session(conn, payload.get("session_id"))
    _check_owner(session, auth_ctx)
    if session["status"] == "active":
        now = _utcnow()
        conn.execute(
            "UPDATE quiz_sessions SET status = 'aborted', updated_at = ? WHERE id = ?",
            (now, session["id"]),
        )
        conn.commit()
    result = json.loads(session["result_json"]) if session["result_json"] else None
    return {
        "session_id": session["id"],
        "aborted": True,
        "result": result,
    }


# ---------- 读取：单次结果 / 历史 / 错题 / 图谱 / 趋势 ----------

STATUS_TESTED = {"mastered", "unstable", "weak"}
MARK_STATUSES = {"open", "mastered", "ignored"}


def normalize_result(result: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """补齐旧结果缺失的字段（mastery_level / max_correct_difficulty / 计数）。"""
    if not result:
        return None
    counts = dict(result.get("counts") or {})
    for key in ("mastered", "unstable", "weak", "untested", "insufficient", "proficient"):
        counts.setdefault(key, 0)
    assessments = []
    for raw in result.get("assessments") or []:
        item = dict(raw)
        item.setdefault("mastery_level", item.get("status"))
        item.setdefault("max_correct_difficulty", None)
        if "asked_count" not in item:
            item["asked_count"] = len(item.get("asked") or [])
        if "wrong_count" not in item:
            item["wrong_count"] = len(item.get("wrong") or [])
        assessments.append(item)
    return {**result, "counts": counts, "assessments": assessments}


def get_session(conn, auth_ctx, session_id: str) -> Dict[str, Any]:
    """按 session_id 读取一次诊断；所有者校验后返回结果或当前题目。"""
    session = _load_session(conn, session_id)
    _check_owner(session, auth_ctx)
    dataset = load_dataset()
    # 旧会话没有 dataset_version：按文档回退到锁定的数据源提交。
    version = session["dataset_version"] or pansgo.SOURCE_COMMIT
    result = (
        normalize_result(json.loads(session["result_json"]))
        if session["result_json"]
        else None
    )
    progress = None
    question = None
    if session["status"] == "active":
        try:
            provider = DBQuestionProvider(conn, version)
            engine = QuizEngine.resume(
                dataset.topics,
                dataset.graph,
                provider,
                json.loads(session["state_json"]),
            )
            question = engine.current_question()
            progress = engine.progress()
        except Exception:
            # 题库已变化时仍可返回会话元信息，由前端提示重新开始。
            question = None

    counts = (result or {}).get("counts", {})
    assessments = (result or {}).get("assessments", [])
    return {
        "session_id": session["id"],
        "mode": session["mode"],
        "grade": session["grade"],
        "semester": session["semester"],
        "status": session["status"],
        "created_at": session["created_at"],
        "finished_at": session["finished_at"],
        "settings": {
            "max_questions": session["max_questions"],
            "mastery_streak": session["mastery_streak"],
        },
        "dataset_version": version,
        "scope_count": (
            session["scope_count"]
            if session["scope_count"] is not None
            else _scope_count(session)
        ),
        "answered": (result or {}).get("answered", (progress or {}).get("answered", 0)),
        "counts": counts,
        "assessments": assessments,
        "weak": (result or {}).get("weak", []),
        "root_causes": (result or {}).get("root_causes", []),
        "learning_path": (result or {}).get("learning_path", []),
        "chapters": (result or {}).get("chapters", []),
        "question": question,
        "progress": progress,
    }


def latest_session(conn, user_id: str) -> Dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, created_at, mode, grade FROM quiz_sessions "
        "WHERE user_id = ? AND status = 'completed' "
        "ORDER BY created_at DESC, id DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "session_id": row["id"],
        "created_at": row["created_at"],
        "mode": row["mode"],
        "grade": row["grade"],
    }


def list_sessions(
    conn,
    user_id: str,
    *,
    limit: int = 20,
    cursor: str | None = None,
    grade: int | None = None,
) -> Dict[str, Any]:
    limit = _clamp_limit(limit)
    where = ["user_id = ?", "status = 'completed'"]
    params: List[Any] = [user_id]
    if grade is not None:
        where.append("grade = ?")
        params.append(int(grade))
    if cursor:
        ts, _, sid = cursor.partition("|")
        where.append("(created_at < ? OR (created_at = ? AND id < ?))")
        params.extend([ts, ts, sid])
    params.append(limit + 1)
    rows = conn.execute(
        f"SELECT * FROM quiz_sessions WHERE {' AND '.join(where)} "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        params,
    ).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [_session_list_item(row) for row in rows]
    next_cursor = (
        f"{rows[-1]['created_at']}|{rows[-1]['id']}"
        if has_more and rows
        else None
    )
    return {"items": items, "next_cursor": next_cursor}


def list_wrong_questions(
    conn,
    user_id: str,
    *,
    grade: int | None = None,
    chapter: str | None = None,
    node_key: str | None = None,
    status: str = "open",
    days: int | None = None,
    limit: int = 20,
    cursor: str | None = None,
) -> Dict[str, Any]:
    """按 dataset_version + question_id 聚合当前用户的错题。"""
    dataset = load_dataset()
    limit = _clamp_limit(limit)
    if status not in MARK_STATUSES and status != "all":
        raise ApiError(400, "INVALID_STATUS", "status 只能是 open / mastered / ignored / all")

    rows = conn.execute(
        "SELECT a.id AS attempt_id, a.session_id, a.question_id, a.node_key, "
        "       a.student_answer, a.created_at, a.dataset_version, a.difficulty, "
        "       a.topic_name, a.chapter, a.grade, a.prompt_snapshot, "
        "       a.choices_snapshot_json, a.answer_snapshot, a.explanation_snapshot, "
        "       a.figure_snapshot "
        "FROM quiz_attempts a JOIN quiz_sessions s ON s.id = a.session_id "
        "WHERE s.user_id = ? AND a.is_correct = 0 "
        "ORDER BY a.created_at DESC, a.id DESC",
        (user_id,),
    ).fetchall()

    groups: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        version = row["dataset_version"] or pansgo.SOURCE_COMMIT
        key = (version, row["question_id"])
        group = groups.get(key)
        if group is None:
            group = _wrong_group(conn, row, version, dataset)
            groups[key] = group
        group["wrong_count"] += 1

    marks: Dict[tuple, str] = {}
    for mark in conn.execute(
        "SELECT dataset_version, question_id, status FROM wrong_question_marks "
        "WHERE user_id = ?",
        (user_id,),
    ):
        marks[(mark["dataset_version"], mark["question_id"])] = mark["status"]

    cutoff = _days_ago(days) if days else None
    # mark_counts 用于「复习进度」，只受时间筛选影响，不随状态筛选变化。
    mark_counts = {"open": 0, "mastered": 0, "ignored": 0}
    base: List[Dict[str, Any]] = []
    for key, group in groups.items():
        group["mark_status"] = marks.get(key, "open")
        if cutoff and group["last_wrong_at"] < cutoff:
            continue
        mark_counts[group["mark_status"]] += 1
        if status != "all" and group["mark_status"] != status:
            continue
        base.append(group)

    # 筛选项来自「状态 + 时间」过滤后的集合，切换年级/章节不会让选项消失。
    grade_counts: Dict[int, int] = {}
    chapter_counts: Dict[str, Dict[str, Any]] = {}
    for group in base:
        if group.get("grade") is not None:
            grade_counts[group["grade"]] = grade_counts.get(group["grade"], 0) + 1
        chapter_key = group.get("chapter")
        if chapter_key:
            entry = chapter_counts.setdefault(
                chapter_key,
                {
                    "chapter": chapter_key,
                    "label": group.get("chapter_label") or chapter_key,
                    "count": 0,
                },
            )
            entry["count"] += 1

    items = [
        group
        for group in base
        if (grade is None or group.get("grade") == grade)
        and (not chapter or group.get("chapter") == chapter)
        and (not node_key or group.get("node_key") == node_key)
    ]

    # 知识点聚合：供错题页的「知识点分布」色块使用。
    node_map: Dict[str, Dict[str, Any]] = {}
    for group in items:
        entry = node_map.get(group["node_key"])
        if entry is None:
            entry = {
                "node_key": group["node_key"],
                "node_name": group["node_name"],
                "chapter": group.get("chapter"),
                "chapter_label": group.get("chapter_label"),
                "wrong_count": 0,
                "question_count": 0,
                "last_wrong_at": group["last_wrong_at"],
                "mark_status": group["mark_status"],
            }
            node_map[group["node_key"]] = entry
        entry["wrong_count"] += group["wrong_count"]
        entry["question_count"] += 1
        if group["last_wrong_at"] > entry["last_wrong_at"]:
            entry["last_wrong_at"] = group["last_wrong_at"]
            entry["mark_status"] = group["mark_status"]

    nodes = sorted(
        node_map.values(), key=lambda n: (-n["wrong_count"], n["node_name"])
    )
    summary = {
        "total": len(items),
        "node_count": len(nodes),
        "oldest_at": min(
            (group["last_wrong_at"] for group in items), default=None
        ),
    }

    items.sort(key=lambda g: (g["last_wrong_at"], g["question_id"]), reverse=True)
    total = len(items)
    if cursor:
        ts, _, qid = cursor.partition("|")
        items = [
            item
            for item in items
            if (item["last_wrong_at"], item["question_id"]) < (ts, qid)
        ]
    page = items[:limit]
    next_cursor = (
        f"{page[-1]['last_wrong_at']}|{page[-1]['question_id']}"
        if len(items) > limit and page
        else None
    )
    return {
        "items": page,
        "next_cursor": next_cursor,
        "total": total,
        "summary": summary,
        "mark_counts": mark_counts,
        "nodes": nodes,
        "grades": [
            {"grade": value, "count": grade_counts[value]}
            for value in sorted(grade_counts)
        ],
        "chapters": sorted(chapter_counts.values(), key=lambda c: c["chapter"]),
    }


def mark_wrong_question(
    conn, user_id: str, attempt_id: int, status: str
) -> Dict[str, Any]:
    if status not in MARK_STATUSES:
        raise ApiError(400, "INVALID_STATUS", "status 只能是 open / mastered / ignored")
    row = conn.execute(
        "SELECT a.id, a.question_id, a.node_key, a.dataset_version "
        "FROM quiz_attempts a JOIN quiz_sessions s ON s.id = a.session_id "
        "WHERE a.id = ? AND s.user_id = ? AND a.is_correct = 0",
        (attempt_id, user_id),
    ).fetchone()
    if row is None:
        raise ApiError(404, "ATTEMPT_NOT_FOUND", "错题记录不存在")
    version = row["dataset_version"] or pansgo.SOURCE_COMMIT
    now = _utcnow()
    conn.execute(
        "INSERT INTO wrong_question_marks "
        "(user_id, dataset_version, question_id, node_key, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, dataset_version, question_id) DO UPDATE SET "
        " status = excluded.status, node_key = excluded.node_key, "
        " updated_at = excluded.updated_at",
        (user_id, version, row["question_id"], row["node_key"], status, now),
    )
    conn.commit()
    return {
        "attempt_id": row["id"],
        "question_id": row["question_id"],
        "status": status,
        "updated_at": now,
    }


def graph_payload(
    conn,
    auth_ctx,
    *,
    session_id: str | None = None,
    node_keys: List[str] | None = None,
    depth: int = 2,
) -> Dict[str, Any]:
    """构建分层先修图：种子 + 向上 depth 层先修。"""
    dataset = load_dataset()
    seeds = _dedupe([str(k) for k in (node_keys or []) if k])
    status_map: Dict[str, Dict[str, Any]] = {}

    if session_id:
        session = _load_session(conn, session_id)
        _check_owner(session, auth_ctx)
        result = (
            normalize_result(json.loads(session["result_json"]))
            if session["result_json"]
            else None
        )
        if result:
            for item in result["assessments"]:
                status_map[item["id"]] = {
                    "status": item["status"],
                    "mastery_level": item.get("mastery_level") or item["status"],
                    "asked_count": item.get(
                        "asked_count", len(item.get("asked") or [])
                    ),
                    "wrong_count": item.get(
                        "wrong_count", len(item.get("wrong") or [])
                    ),
                }
                if item["status"] in ("weak", "unstable"):
                    seeds.append(item["id"])

    seeds = _dedupe(seeds)
    if not seeds:
        raise ApiError(400, "MISSING_SEEDS", "请至少选择一个知识点或提供 session_id")
    unknown = [s for s in seeds if s not in dataset.topics]
    if unknown:
        raise ApiError(
            400, "UNKNOWN_TOPIC", f"知识点不在数据集中：{unknown[0]}"
        )
    try:
        depth = max(1, min(3, int(depth)))
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_DEPTH", "depth 必须是 1–3") from None

    nodes, edges = _layered_graph(dataset, seeds, depth, status_map)
    return {"seeds": seeds, "nodes": nodes, "edges": edges}


def build_trends(
    conn,
    user_id: str,
    *,
    grade: int | None = None,
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
) -> Dict[str, Any]:
    dataset = load_dataset()
    limit = _clamp_limit(limit, default=10)
    where = ["user_id = ?", "status = 'completed'"]
    params: List[Any] = [user_id]
    if grade is not None:
        where.append("grade = ?")
        params.append(int(grade))
    if date_from:
        where.append("created_at >= ?")
        params.append(date_from)
    if date_to:
        where.append("created_at <= ?")
        params.append(date_to)
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM quiz_sessions WHERE {' AND '.join(where)} "
        "ORDER BY created_at DESC, id DESC LIMIT ?",
        params,
    ).fetchall()
    rows = list(reversed(rows))

    empty = {
        "range": {
            "from": rows[0]["created_at"] if rows else None,
            "to": rows[-1]["created_at"] if rows else None,
            "session_count": len(rows),
        },
        "sessions": [],
        "points": [],
        "continuous_weak": [],
        "improved": [],
        "repeated_wrong": [],
        "version_breaks": [],
        "reason": "not_enough_sessions",
    }
    if len(rows) < 2:
        return empty

    session_items: List[Dict[str, Any]] = []
    points: Dict[str, Dict[str, Any]] = {}
    version_breaks: List[Dict[str, Any]] = []
    previous_version: str | None = None
    previous_id: str | None = None
    # 同版本连续会话为一段；版本变化后开启新段，跨段不做“持续/改善”比较。
    segment = 0

    for row in rows:
        version = row["dataset_version"] or pansgo.SOURCE_COMMIT
        result = (
            normalize_result(json.loads(row["result_json"]))
            if row["result_json"]
            else None
        )
        counts = (result or {}).get("counts", {})
        scope_count = (
            row["scope_count"]
            if row["scope_count"] is not None
            else _scope_count(row)
        )
        assessed, mastery_rate, weak_rate, coverage = _trend_metrics(counts, scope_count)
        session_items.append(
            {
                "session_id": row["id"],
                "created_at": row["created_at"],
                "mode": row["mode"],
                "grade": row["grade"],
                "dataset_version": version,
                "assessed": assessed,
                "counts": counts,
                "mastery_rate": mastery_rate,
                "weak_rate": weak_rate,
                "coverage": coverage,
            }
        )

        if previous_version is not None and version != previous_version:
            version_breaks.append(
                {"after_session": previous_id, "before_session": row["id"]}
            )
            segment += 1
        previous_version = version
        previous_id = row["id"]

        for item in (result or {}).get("assessments", []):
            if item["status"] not in STATUS_TESTED:
                continue
            entry = points.setdefault(
                item["id"],
                {
                    "node_key": item["id"],
                    "name": item.get("name") or item["id"],
                    "chapter": item.get("chapter"),
                    "chapter_label": item.get("chapter_label"),
                    "history": [],
                },
            )
            entry["history"].append(
                {
                    "session_id": row["id"],
                    "created_at": row["created_at"],
                    "dataset_version": version,
                    "segment": segment,
                    "status": item["status"],
                    "mastery_level": item.get("mastery_level") or item["status"],
                }
            )

    continuous_weak: List[Dict[str, Any]] = []
    improved: Dict[str, Dict[str, Any]] = {}
    for node_key, point in points.items():
        history = point["history"]
        streak = 0
        latest_segment = history[-1]["segment"] if history else 0
        for entry in reversed(history):
            if entry["segment"] != latest_segment:
                break
            if entry["status"] == "weak":
                streak += 1
            else:
                break
        if streak >= 2:
            continuous_weak.append(
                {
                    "node_key": node_key,
                    "name": point["name"],
                    "count": streak,
                    "last_status": "weak",
                }
            )
        for index in range(1, len(history)):
            prev, cur = history[index - 1], history[index]
            if prev["segment"] != cur["segment"]:
                continue
            if prev["status"] in ("weak", "unstable") and cur["mastery_level"] in (
                "mastered",
                "proficient",
            ):
                improved[node_key] = {
                    "node_key": node_key,
                    "name": point["name"],
                    "from": prev["status"],
                    "to": cur["mastery_level"],
                    "at_session": cur["session_id"],
                }

    repeated_wrong: List[Dict[str, Any]] = []
    window_ids = [row["id"] for row in rows]
    placeholders = ",".join("?" for _ in window_ids)
    for row in conn.execute(
        "SELECT a.question_id, a.node_key, COUNT(*) AS c "
        "FROM quiz_attempts a "
        f"WHERE a.session_id IN ({placeholders}) AND a.is_correct = 0 "
        "GROUP BY a.question_id, a.node_key HAVING c >= 2 "
        "ORDER BY c DESC, a.question_id",
        window_ids,
    ):
        topic = dataset.topics.get(row["node_key"], {})
        repeated_wrong.append(
            {
                "question_id": row["question_id"],
                "node_key": row["node_key"],
                "name": topic.get("name") or row["node_key"],
                "wrong_count": row["c"],
            }
        )

    point_list = list(points.values())
    point_list.sort(key=lambda p: (-len(p["history"]), p["name"]))
    continuous_weak.sort(key=lambda c: (-c["count"], c["name"]))

    return {
        "range": {
            "from": rows[0]["created_at"],
            "to": rows[-1]["created_at"],
            "session_count": len(rows),
        },
        "sessions": session_items,
        "points": point_list,
        "continuous_weak": continuous_weak,
        "improved": list(improved.values()),
        "repeated_wrong": repeated_wrong,
        "version_breaks": version_breaks,
        "reason": None,
    }


# ---------- 内部 ----------


def _session_list_item(row) -> Dict[str, Any]:
    result = (
        normalize_result(json.loads(row["result_json"]))
        if row["result_json"]
        else None
    )
    counts = (result or {}).get("counts", {})
    scope_count = (
        row["scope_count"] if row["scope_count"] is not None else _scope_count(row)
    )
    assessed, mastery_rate, _weak_rate, coverage = _trend_metrics(counts, scope_count)
    return {
        "session_id": row["id"],
        "created_at": row["created_at"],
        "mode": row["mode"],
        "grade": row["grade"],
        "status": row["status"],
        "dataset_version": row["dataset_version"] or pansgo.SOURCE_COMMIT,
        "answered": (result or {}).get("answered", 0),
        "counts": counts,
        "assessed": assessed,
        "mastery_rate": mastery_rate,
        "coverage": coverage,
    }


def _trend_metrics(counts: Dict[str, int], scope_count) -> tuple:
    assessed = (
        counts.get("mastered", 0)
        + counts.get("unstable", 0)
        + counts.get("weak", 0)
    )
    # mastered 已包含 proficient，直接用 mastered / 已测。
    mastery_rate = round(counts.get("mastered", 0) / assessed, 4) if assessed else None
    weak_rate = round(counts.get("weak", 0) / assessed, 4) if assessed else None
    coverage = round(assessed / scope_count, 4) if scope_count else None
    return assessed, mastery_rate, weak_rate, coverage


def _scope_count(session) -> int | None:
    try:
        scope = json.loads(session["scope_json"]) if session["scope_json"] else {}
    except (TypeError, ValueError):
        return None
    node_ids = scope.get("node_ids") if isinstance(scope, dict) else None
    return len(node_ids) if isinstance(node_ids, list) else None


def _wrong_group(conn, row, version: str, dataset: Dataset) -> Dict[str, Any]:
    topic = dataset.topics.get(row["node_key"], {})
    fallback = None
    if row["prompt_snapshot"] is None or row["answer_snapshot"] is None:
        fallback = _question_fallback(conn, version, row["question_id"])
    fallback = fallback or {}
    chapter = row["chapter"] or fallback.get("chapter") or topic.get("chapter")
    return {
        "attempt_id": row["attempt_id"],
        "session_id": row["session_id"],
        "dataset_version": version,
        "question_id": row["question_id"],
        "node_key": row["node_key"],
        "node_name": (
            row["topic_name"]
            or fallback.get("node_name")
            or topic.get("name")
            or row["node_key"]
        ),
        "chapter": chapter,
        "chapter_label": topic.get("chapter_label") or chapter,
        "grade": (
            row["grade"]
            if row["grade"] is not None
            else fallback.get("grade", topic.get("grade"))
        ),
        "difficulty": row["difficulty"] or fallback.get("difficulty"),
        "prompt": row["prompt_snapshot"] or fallback.get("prompt") or "",
        "choices": (
            json.loads(row["choices_snapshot_json"])
            if row["choices_snapshot_json"]
            else fallback.get("choices") or []
        ),
        "figure": (
            row["figure_snapshot"]
            if row["figure_snapshot"] is not None
            else fallback.get("figure") or ""
        ),
        "student_answer": row["student_answer"],
        "correct_answer": (
            row["answer_snapshot"]
            if row["answer_snapshot"] is not None
            else fallback.get("answer")
        ),
        "explanation": (
            row["explanation_snapshot"]
            if row["explanation_snapshot"] is not None
            else fallback.get("explanation")
        ),
        "wrong_count": 0,
        "last_wrong_at": row["created_at"],
        "mark_status": "open",
    }


def _question_fallback(conn, version: str, question_id: str) -> Dict[str, Any] | None:
    try:
        row = conn.execute(
            "SELECT node_name, grade, chapter, difficulty, prompt, choices_json, "
            "       answer, explanation, figure_svg "
            "FROM questions WHERE dataset_version = ? AND id = ?",
            (version, question_id),
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    return {
        "node_name": row["node_name"],
        "grade": row["grade"],
        "chapter": row["chapter"],
        "difficulty": row["difficulty"],
        "prompt": row["prompt"],
        "choices": json.loads(row["choices_json"]) if row["choices_json"] else [],
        "answer": row["answer"],
        "explanation": row["explanation"],
        "figure": row["figure_svg"],
    }


def _layered_graph(
    dataset: Dataset,
    seeds: List[str],
    depth: int,
    status_map: Dict[str, Dict[str, Any]],
) -> tuple:
    graph = dataset.graph
    level: Dict[str, int] = {seed: 0 for seed in seeds}
    frontier = list(seeds)
    for current_depth in range(1, depth + 1):
        next_frontier: List[str] = []
        for node in frontier:
            if node not in graph:
                continue
            for parent in graph.predecessors(node):
                if parent not in level:
                    level[parent] = current_depth
                    next_frontier.append(parent)
        frontier = next_frontier

    included = set(level)
    nodes = []
    for node_id, node_depth in level.items():
        topic = dataset.topics.get(node_id, {})
        state = status_map.get(node_id) or {}
        nodes.append(
            {
                "id": node_id,
                "name": topic.get("name") or node_id,
                "grade": topic.get("grade"),
                "chapter": topic.get("chapter"),
                "chapter_label": topic.get("chapter_label"),
                "status": state.get("status"),
                "mastery_level": state.get("mastery_level"),
                "asked_count": state.get("asked_count"),
                "wrong_count": state.get("wrong_count"),
                "depth": node_depth,
            }
        )
    nodes.sort(key=lambda n: (-n["depth"], n["grade"] or 0, n["name"]))

    edges = []
    for source, target in graph.edges():
        if source in included and target in included:
            data = graph.get_edge_data(source, target) or {}
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "strength": data.get("strength") or "hard",
                    "type": "prerequisites_for",
                }
            )
    return nodes, edges


def _days_ago(days: int) -> str:
    return _iso(datetime.now(timezone.utc) - timedelta(days=int(days)))


def _clamp_limit(limit, default: int = 20) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(100, value))


def _find_question(provider, node_id, question_id):
    if not node_id:
        return None
    for question in provider(node_id):
        if question.id == question_id:
            return question
    return None


def _attempt_snapshot(dataset: Dataset, node_id, question) -> Dict[str, Any]:
    topic = dataset.topics.get(node_id or "", {})
    if question is None:
        return {
            "dataset_version": dataset.version,
            "difficulty": None,
            "topic_name": topic.get("name"),
            "chapter": topic.get("chapter"),
            "grade": topic.get("grade"),
            "prompt": None,
            "choices_json": None,
            "answer": None,
            "explanation": None,
            "figure": None,
        }
    return {
        "dataset_version": dataset.version,
        "difficulty": question.difficulty,
        "topic_name": topic.get("name"),
        "chapter": topic.get("chapter"),
        "grade": topic.get("grade"),
        "prompt": question.prompt,
        "choices_json": json.dumps(
            [dict(choice) for choice in question.choices], ensure_ascii=False
        ),
        "answer": str(question.answer) if question.answer is not None else "",
        "explanation": question.explanation,
        "figure": question.figure,
    }


def pansgo_mode_names() -> set:
    return {"single", "chapter", "grade"}


def _resolve_scope(dataset: Dataset, mode: str, payload: Dict[str, Any]):
    if mode == "grade":
        grade = payload.get("grade")
        if not isinstance(grade, int):
            raise ApiError(400, "INVALID_SCOPE", "整年级摸底需要 grade")
        grade_topics = [t for t in dataset.topics.values() if t.get("grade") == grade]
        if not grade_topics:
            raise ApiError(400, "INVALID_SCOPE", f"没有 {grade} 年级的知识点")
        semester = str(payload.get("semester") or "all")
        semesters = {t.get("semester") for t in grade_topics if t.get("semester")}
        if semester != "all" and semester not in semesters:
            raise ApiError(400, "INVALID_SCOPE", f"{grade} 年级没有「{semester}」册")
        node_ids = [
            t["id"]
            for t in grade_topics
            if semester == "all" or t.get("semester") == semester
        ]
        node_ids = _dedupe(node_ids)[:MAX_SCOPE_NODES]
        return node_ids, grade, semester

    raw_ids = payload.get("node_ids") or []
    if not isinstance(raw_ids, list):
        raise ApiError(400, "INVALID_SCOPE", "node_ids 必须是数组")
    node_ids = _dedupe([str(x) for x in raw_ids if x])
    if mode == "single" and len(node_ids) != 1:
        raise ApiError(400, "INVALID_SCOPE", "单点诊断只能选择 1 个知识点")
    if not node_ids:
        raise ApiError(400, "INVALID_SCOPE", "请选择至少 1 个知识点")
    if len(node_ids) > MAX_SCOPE_NODES:
        raise ApiError(400, "INVALID_SCOPE", f"一次最多选择 {MAX_SCOPE_NODES} 个知识点")
    unknown = [n for n in node_ids if n not in dataset.topics]
    if unknown:
        raise ApiError(
            400, "UNKNOWN_TOPIC", f"有 {len(unknown)} 个知识点不在数据集中，例如 {unknown[0]}"
        )
    # 单点/章节诊断也要落年级快照，否则按年级筛选趋势时这些会话会整批消失。
    # 跨年级混合范围不写年级，保持 NULL，避免污染按年级的趋势统计。
    grades = {
        dataset.topics[str(node_id)].get("grade")
        for node_id in node_ids
        if dataset.topics.get(str(node_id), {}).get("grade") is not None
    }
    derived_grade = grades.pop() if len(grades) == 1 else None
    return node_ids, derived_grade, None


def _param(payload, name, default, bounds):
    raw = payload.get(name)
    if raw is None or raw == "":
        value = default
    else:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ApiError(400, "INVALID_PARAM", f"{name} 必须是整数") from None
    low, high = bounds
    if not low <= value <= high:
        raise ApiError(400, "INVALID_PARAM", f"{name} 必须在 {low}–{high} 之间")
    return value


def _dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _load_session(conn, session_id):
    if not session_id:
        raise ApiError(400, "INVALID_SESSION", "缺少 session_id")
    row = conn.execute(
        "SELECT * FROM quiz_sessions WHERE id = ?", (str(session_id),)
    ).fetchone()
    if row is None:
        raise ApiError(404, "SESSION_NOT_FOUND", "诊断会话不存在")
    return row


def _check_owner(session, auth_ctx) -> None:
    if session["user_id"] is None:
        return
    if auth_ctx is None or auth_ctx.user["id"] != session["user_id"]:
        raise ApiError(404, "SESSION_NOT_FOUND", "诊断会话不存在")


def _check_active(session) -> None:
    if session["status"] != "active":
        raise ApiError(409, "SESSION_FINISHED", "本次诊断已经结束")
    if session["expires_at"] <= now_utc():
        raise ApiError(410, "SESSION_EXPIRED", "诊断会话已过期，请重新开始")


def _session_payload(session_id: str, engine: QuizEngine, result) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "mode": engine.state["mode"],
        "settings": {
            "max_questions": engine.state["max_questions"],
            "mastery_streak": engine.state["mastery_streak"],
        },
        "question": engine.current_question(),
        "progress": engine.progress(),
        "result": result,
        "persisted": True,
    }


def _utcnow() -> str:
    return now_utc()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
