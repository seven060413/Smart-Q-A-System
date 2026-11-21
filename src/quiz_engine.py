"""学情诊断引擎：单点 / 章节 / 整年级摸底。

规则（与产品约定一致）：

- 每个知识点按难度阶梯出题：基础 → 提高 → 拓展；
- 连续答对 ``mastery_streak`` 题判为「掌握」；题量不足时按实际题量判定；
- 答错立即终止该点的掌握判定，并追加 **1 道确认题**（同级或降一级）：
  - 确认题答对 → 「不稳」；
  - 确认题答错 → 「薄弱」，并回溯先修知识点；
- 总题量到上限后，未测完的知识点标为「未测」；
- 可用题目少于 2 道时标为「题量不足」。

引擎只依赖纯数据：知识点字典、先修图（networkx DiGraph，边 source→target 表示
source 是先学）和题目读取函数。状态是一个可 JSON 序列化的 dict，便于落库和恢复。
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import networkx as nx

from .question_bank import Question, grade_answer

STATUS_PENDING = "pending"
STATUS_MASTERED = "mastered"
STATUS_UNSTABLE = "unstable"
STATUS_WEAK = "weak"
STATUS_UNTESTED = "untested"
STATUS_INSUFFICIENT = "insufficient"

TERMINAL_STATUSES = {
    STATUS_MASTERED,
    STATUS_UNSTABLE,
    STATUS_WEAK,
    STATUS_UNTESTED,
    STATUS_INSUFFICIENT,
}

DIFFICULTY_RANK = {"basic": 0, "standard": 1, "challenge": 2, "advanced": 2}
RANK_DIFFICULTY = {0: "basic", 1: "standard", 2: "challenge"}

# 掌握等级：mastered 内部再分「熟练 / 掌握」。
# 最高答对难度达到 challenge / advanced 记熟练，否则记掌握。
MASTERY_PROFICIENT = "proficient"
PROFICIENT_DIFFICULTIES = {"challenge", "advanced"}
# 和 DIFFICULTY_RANK 不同：advanced 比 challenge 更高，用于「最高答对难度」。
DIFFICULTY_LEVEL = {"basic": 0, "standard": 1, "challenge": 2, "advanced": 3}

MODE_SINGLE = "single"
MODE_CHAPTER = "chapter"
MODE_GRADE = "grade"
MODES = {MODE_SINGLE, MODE_CHAPTER, MODE_GRADE}

START_DIFFICULTY = {
    MODE_SINGLE: "basic",
    MODE_CHAPTER: "basic",
    MODE_GRADE: "standard",
}

# 薄弱后向上回溯的层数上限；整年级摸底以覆盖面优先，只回一层。
MAX_BACKTRACK_DEPTH = {
    MODE_SINGLE: 3,
    MODE_CHAPTER: 3,
    MODE_GRADE: 1,
}

QuestionLoader = Callable[[str], Sequence[Question]]


class QuizStateError(Exception):
    """会话状态不合法（题号不匹配、已完成等）。"""


class QuizEngine:
    """一次诊断会话的纯逻辑状态机。"""

    def __init__(
        self,
        topics: Dict[str, Dict[str, Any]],
        prerequisites: nx.DiGraph,
        questions_for: QuestionLoader,
        state: Dict[str, Any],
    ):
        self.topics = topics
        self.prerequisites = prerequisites
        self.questions_for = questions_for
        self.state = state

    # ---------- 构造 ----------

    @classmethod
    def start(
        cls,
        topics: Dict[str, Dict[str, Any]],
        prerequisites: nx.DiGraph,
        questions_for: QuestionLoader,
        *,
        mode: str,
        node_ids: Iterable[str],
        max_questions: int,
        mastery_streak: int,
    ) -> "QuizEngine":
        if mode not in MODES:
            raise ValueError(f"未知诊断模式: {mode}")
        if mastery_streak not in (2, 3, 5):
            raise ValueError("mastery_streak 只能是 2 / 3 / 5")
        if max_questions < 1:
            raise ValueError("max_questions 至少为 1")

        valid_ids = [n for n in node_ids if n in topics]
        if not valid_ids:
            raise ValueError("诊断范围里没有有效知识点")

        queue = _order_nodes(topics, valid_ids)
        state: Dict[str, Any] = {
            "version": 1,
            "mode": mode,
            "max_questions": int(max_questions),
            "mastery_streak": int(mastery_streak),
            "start_difficulty": START_DIFFICULTY[mode],
            "queue": queue,
            "cursor": 0,
            "answered": 0,
            "nodes": {},
            "current_node": None,
            "current_question": None,
            "finished": False,
        }
        engine = cls(topics, prerequisites, questions_for, state)
        engine._advance_to_next()
        return engine

    @classmethod
    def resume(
        cls,
        topics: Dict[str, Dict[str, Any]],
        prerequisites: nx.DiGraph,
        questions_for: QuestionLoader,
        state: Dict[str, Any],
    ) -> "QuizEngine":
        return cls(topics, prerequisites, questions_for, state)

    # ---------- 查询 ----------

    def current_question(self) -> Optional[Dict[str, Any]]:
        node_id = self.state.get("current_node")
        question_id = self.state.get("current_question")
        if not node_id or not question_id:
            return None
        question = self._find_question(node_id, question_id)
        return public_question(self.topics, node_id, question) if question else None

    def progress(self) -> Dict[str, Any]:
        node_id = self.state.get("current_node")
        node_state = self.state["nodes"].get(node_id or "", {})
        counts = Counter(ns["status"] for ns in self.state["nodes"].values())
        return {
            "answered": self.state["answered"],
            "max_questions": self.state["max_questions"],
            "current_node": node_id,
            "current_node_name": (self.topics.get(node_id or "") or {}).get("name"),
            "streak": node_state.get("streak", 0),
            "mastery_streak": self.state["mastery_streak"],
            "counts": dict(counts),
            "finished": self.state["finished"],
        }

    def result(self) -> Dict[str, Any]:
        assessments = []
        for node_id, ns in self.state["nodes"].items():
            topic = self.topics.get(node_id, {})
            history = list(ns.get("history") or [])
            max_correct = _max_correct_difficulty(history)
            mastery_level = _mastery_level(ns["status"], max_correct)
            assessments.append(
                {
                    "id": node_id,
                    "name": topic.get("name") or node_id,
                    "grade": topic.get("grade"),
                    "chapter": topic.get("chapter"),
                    "chapter_label": topic.get("chapter_label"),
                    "status": ns["status"],
                    "mastery_level": mastery_level,
                    "max_correct_difficulty": max_correct,
                    "streak": ns["streak"],
                    "asked": list(ns["asked"]),
                    "wrong": list(ns["wrong"]),
                    "asked_count": len(ns["asked"]),
                    "wrong_count": len(ns["wrong"]),
                    "effective_mastery": min(
                        self.state["mastery_streak"], len(self._available(node_id))
                    ),
                    "depth": ns.get("depth", 0),
                }
            )

        counts = Counter(a["status"] for a in assessments)
        proficient = sum(
            1 for a in assessments if a["mastery_level"] == MASTERY_PROFICIENT
        )
        weak = [a for a in assessments if a["status"] == STATUS_WEAK]
        weak_ids = {a["id"] for a in weak}
        root_causes = [
            a["id"]
            for a in weak
            if not any(
                p in weak_ids for p in _safe_predecessors(self.prerequisites, a["id"])
            )
        ]
        depth = {a["id"]: a["depth"] for a in assessments}
        learning_path = sorted(
            weak_ids, key=lambda n: (-depth.get(n, 0), _node_order_key(self.topics, n))
        )

        return {
            "mode": self.state["mode"],
            "finished": self.state["finished"],
            "answered": self.state["answered"],
            "max_questions": self.state["max_questions"],
            "counts": {
                # mastered 是「熟练 + 掌握」的合计，保持既有前端语义；
                # proficient 是 mastered 的子集。
                "mastered": counts.get(STATUS_MASTERED, 0),
                "proficient": proficient,
                "unstable": counts.get(STATUS_UNSTABLE, 0),
                "weak": counts.get(STATUS_WEAK, 0),
                "untested": counts.get(STATUS_UNTESTED, 0),
                "insufficient": counts.get(STATUS_INSUFFICIENT, 0),
            },
            "assessments": assessments,
            "weak": [a["id"] for a in weak],
            "root_causes": root_causes,
            "learning_path": learning_path,
            "chapters": self._chapter_summary(assessments),
        }

    # ---------- 作答 ----------

    def answer(self, question_id: str, response: Any) -> Dict[str, Any]:
        state = self.state
        if state["finished"]:
            raise QuizStateError("本次诊断已经结束")
        node_id = state.get("current_node")
        if not node_id or state.get("current_question") != question_id:
            raise QuizStateError("题号与会话当前题目不一致")

        node_state = state["nodes"][node_id]
        question = self._find_question(node_id, question_id)
        if question is None:
            raise QuizStateError("题目不存在")
        correct = grade_answer(question, response)
        if correct is None:
            raise QuizStateError("该题不支持自动判分")

        node_state["asked"].append(question_id)
        # 本次作答历史：供「最高答对难度」与熟练/掌握分级使用；
        # 旧会话恢复时没有这个字段，用 setdefault 兼容。
        node_state.setdefault("history", []).append(
            {
                "question_id": question_id,
                "difficulty": question.difficulty,
                "correct": bool(correct),
            }
        )
        state["answered"] += 1

        terminal = False
        weak = False

        if correct:
            if node_state["confirming"]:
                node_state["status"] = STATUS_UNSTABLE
                terminal = True
            else:
                node_state["streak"] += 1
                if node_state["streak"] >= self._effective_mastery(node_id):
                    node_state["status"] = STATUS_MASTERED
                    terminal = True
                else:
                    next_question = self._pick(
                        node_id,
                        target=min(2, _rank(question.difficulty) + 1),
                        direction="up",
                    )
                    if next_question is None:
                        node_state["status"] = STATUS_INSUFFICIENT
                        terminal = True
                    else:
                        node_state["question"] = next_question.id
                        state["current_question"] = next_question.id
        else:
            node_state["wrong"].append(question_id)
            node_state["streak"] = 0
            if node_state["confirming"]:
                node_state["status"] = STATUS_WEAK
                terminal = True
                weak = True
            else:
                node_state["confirming"] = True
                next_question = self._pick(
                    node_id,
                    target=max(0, _rank(question.difficulty) - 1),
                    direction="down",
                )
                if next_question is None:
                    node_state["status"] = STATUS_INSUFFICIENT
                    terminal = True
                else:
                    node_state["question"] = next_question.id
                    state["current_question"] = next_question.id

        if terminal:
            node_state["question"] = None

        if state["answered"] >= state["max_questions"]:
            if not terminal:
                # 题量到上限，本点还没测完：标为未测。
                node_state["status"] = STATUS_UNTESTED
                node_state["question"] = None
            self._finish_remaining()
        elif terminal:
            self._advance_after_terminal(node_id, weak=weak)

        return {
            "is_correct": correct,
            "explanation": question.explanation,
            "node_status": node_state["status"] if terminal else None,
            "next_question": self.current_question(),
            "result": self.result() if state["finished"] else None,
            "progress": self.progress(),
        }

    # ---------- 内部 ----------

    def _available(self, node_id: str) -> List[Question]:
        return [q for q in self.questions_for(node_id) if q.gradable]

    def _effective_mastery(self, node_id: str) -> int:
        return min(self.state["mastery_streak"], len(self._available(node_id)))

    def _find_question(self, node_id: str, question_id: str) -> Optional[Question]:
        for q in self.questions_for(node_id):
            if q.id == question_id:
                return q
        return None

    def _pick(
        self, node_id: str, *, target: int, direction: str
    ) -> Optional[Question]:
        node_state = self.state["nodes"][node_id]
        asked = set(node_state["asked"])
        candidates = [q for q in self._available(node_id) if q.id not in asked]
        if not candidates:
            return None
        target = max(0, min(2, target))

        def key(q: Question):
            rank = _rank(q.difficulty)
            if direction == "down":
                # 确认题：优先同级或更易
                return (0 if rank <= target else 1, abs(rank - target), -rank, q.id)
            # 正常推进：优先同级或更难
            return (0 if rank >= target else 1, abs(rank - target), rank, q.id)

        return min(candidates, key=key)

    def _advance_after_terminal(self, node_id: str, *, weak: bool) -> None:
        state = self.state
        depth = state["nodes"][node_id].get("depth", 0)
        if weak:
            self._enqueue_prerequisites(node_id, depth)
        state["cursor"] += 1
        state["current_node"] = None
        state["current_question"] = None
        self._advance_to_next()

    def _enqueue_prerequisites(self, node_id: str, depth: int) -> None:
        state = self.state
        if depth >= MAX_BACKTRACK_DEPTH[state["mode"]]:
            return
        if node_id not in self.prerequisites:
            return
        parents = sorted(self.prerequisites.predecessors(node_id))
        for parent in parents:
            if parent not in self.topics or parent in state["nodes"]:
                continue
            if parent in state["queue"]:
                continue
            state["nodes"][parent] = _new_node_state(depth + 1)
            if state["mode"] == MODE_GRADE:
                state["queue"].append(parent)  # 摸底以覆盖优先，回溯点排到最后
            else:
                state["queue"].insert(state["cursor"] + 1, parent)  # 单点/章节优先查根因

    def _advance_to_next(self) -> None:
        state = self.state
        if state["finished"]:
            return
        if state["answered"] >= state["max_questions"]:
            self._finish_remaining()
            return

        while state["cursor"] < len(state["queue"]):
            node_id = state["queue"][state["cursor"]]
            if node_id not in state["nodes"]:
                state["nodes"][node_id] = _new_node_state(0)
            node_state = state["nodes"][node_id]

            if node_state["status"] != STATUS_PENDING:
                state["cursor"] += 1
                continue

            available = self._available(node_id)
            if len(available) < 2:
                node_state["status"] = STATUS_INSUFFICIENT
                state["cursor"] += 1
                continue

            node_state["last_rank"] = _rank(state["start_difficulty"])
            question = self._pick(
                node_id, target=node_state["last_rank"], direction="up"
            )
            if question is None:
                node_state["status"] = STATUS_INSUFFICIENT
                state["cursor"] += 1
                continue

            node_state["question"] = question.id
            state["current_node"] = node_id
            state["current_question"] = question.id
            return

        self._finish_remaining()

    def _finish_remaining(self) -> None:
        state = self.state
        for node_state in state["nodes"].values():
            if node_state["status"] == STATUS_PENDING:
                node_state["status"] = STATUS_UNTESTED
            node_state["question"] = None
        state["current_node"] = None
        state["current_question"] = None
        state["finished"] = True

    def _chapter_summary(self, assessments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chapters: Dict[str, Dict[str, Any]] = {}
        for item in assessments:
            chapter = item.get("chapter") or "未分章"
            entry = chapters.setdefault(
                chapter,
                {
                    "chapter": chapter,
                    "label": item.get("chapter_label") or chapter,
                    "grade": item.get("grade"),
                    "topic_count": 0,
                    "mastered": 0,
                    "proficient": 0,
                    "unstable": 0,
                    "weak": 0,
                    "untested": 0,
                    "insufficient": 0,
                    "weak_nodes": [],
                },
            )
            entry["topic_count"] += 1
            status = item["status"]
            if item.get("mastery_level") == MASTERY_PROFICIENT:
                entry["proficient"] += 1
            if status in entry:
                entry[status] += 1
            if status == STATUS_WEAK:
                entry["weak_nodes"].append({"id": item["id"], "name": item["name"]})
        return sorted(
            chapters.values(),
            key=lambda c: (-c["weak"], -c["unstable"], c["grade"] or 0, c["chapter"]),
        )


def public_question(
    topics: Dict[str, Dict[str, Any]], node_id: str, question: Question
) -> Dict[str, Any]:
    """发给前端的题目：绝不包含 answer / verify。"""
    topic = topics.get(node_id, {})
    return {
        "id": question.id,
        "node_key": node_id,
        "node_name": topic.get("name") or node_id,
        "grade": topic.get("grade"),
        "chapter": topic.get("chapter"),
        "chapter_label": topic.get("chapter_label"),
        "difficulty": question.difficulty,
        "type": question.type,
        "prompt": question.prompt,
        "choices": [dict(c) for c in question.choices],
        "figure": question.figure,
        "hide_choice_text": question.hide_choice_text,
    }


def _new_node_state(depth: int) -> Dict[str, Any]:
    return {
        "status": STATUS_PENDING,
        "streak": 0,
        "asked": [],
        "wrong": [],
        "history": [],
        "confirming": False,
        "last_rank": 0,
        "depth": depth,
        "question": None,
    }


def _max_correct_difficulty(history: List[Dict[str, Any]]) -> Optional[str]:
    """答对题中的最高难度；没有答对过返回 None。"""
    best: Optional[str] = None
    best_level = -1
    for entry in history:
        if not entry.get("correct"):
            continue
        difficulty = str(entry.get("difficulty") or "")
        level = DIFFICULTY_LEVEL.get(difficulty, -1)
        if level > best_level:
            best_level = level
            best = difficulty
    return best


def _mastery_level(status: str, max_correct: Optional[str]) -> str:
    """掌握等级：mastered 内部分熟练/掌握，其他状态沿用诊断状态。"""
    if status == STATUS_MASTERED:
        if max_correct in PROFICIENT_DIFFICULTIES:
            return MASTERY_PROFICIENT
        return STATUS_MASTERED
    return status


def _rank(difficulty: str) -> int:
    return DIFFICULTY_RANK.get(difficulty, 1)


def _order_nodes(
    topics: Dict[str, Dict[str, Any]], node_ids: Sequence[str]
) -> List[str]:
    """按章轮流取点，保证有限题量下尽量覆盖多章。"""
    groups: Dict[tuple, List[str]] = {}
    for node_id in node_ids:
        topic = topics.get(node_id, {})
        key = (topic.get("grade") or 0, topic.get("chapter") or "")
        groups.setdefault(key, []).append(node_id)

    queues = [deque(ids) for ids in groups.values()]
    ordered: List[str] = []
    while any(queues):
        for queue in queues:
            if queue:
                ordered.append(queue.popleft())
    return ordered


def _safe_predecessors(graph: nx.DiGraph, node: str) -> List[str]:
    if node not in graph:
        return []
    return list(graph.predecessors(node))


def _node_order_key(topics: Dict[str, Dict[str, Any]], node_id: str) -> tuple:
    topic = topics.get(node_id, {})
    return (topic.get("grade") or 0, topic.get("chapter") or "", node_id)
