"""cn-math-taxonomy（math.pansgo.com）数学 K12（1–14 年级）数据接入。

本模块只负责过滤、字段映射与结构校验，不修改知识点或题目内容。

数据来源：https://github.com/xiaoyang111222/cn-math-taxonomy
在线站点：https://math.pansgo.com/
许可证：CC BY-NC 4.0（署名—非商业性使用 4.0 国际）
      https://creativecommons.org/licenses/by-nc/4.0/

使用约束：非商业用途；再分发或改编时须署名原作者并注明修改。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SOURCE_REPO = "https://github.com/xiaoyang111222/cn-math-taxonomy"
SOURCE_SITE = "https://math.pansgo.com/"
# 锁定的提交，保证重复构建得到同一份数据。
SOURCE_COMMIT = "f4721bb947d95823ee8a41b2507ad411ff66e5e0"
LICENSE = "CC BY-NC 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
ATTRIBUTION = "知识图谱与题库数据来自 Aifeng（xiaoyang111222）的 cn-math-taxonomy，CC BY-NC 4.0"

DATASET_ID = "pansgo_math_k12"
PRODUCER = "cn-math-taxonomy"
NODE_LABEL = "Concept"
PREREQ_EDGE_TYPE = "prerequisites_for"

# pansgo 的年级编码：1–9 为义务教育年级，10–14 为高中教材册次。
GRADE_LABELS = {
    1: "一年级", 2: "二年级", 3: "三年级", 4: "四年级", 5: "五年级",
    6: "六年级", 7: "七年级", 8: "八年级", 9: "九年级",
    10: "高一", 11: "高二", 12: "选必一", 13: "选必二", 14: "选必三",
}
GRADE_STAGES = {
    1: "小学", 2: "小学", 3: "小学", 4: "小学", 5: "小学", 6: "小学",
    7: "初中", 8: "初中", 9: "初中",
    10: "高中", 11: "高中", 12: "高中", 13: "高中", 14: "高中",
}
MAX_GRADE = 14

# 题目难度从易到难，用于出题排序。challenge 是 pansgo 的部分学科写法。
DIFFICULTY_ORDER = {"basic": 0, "standard": 1, "challenge": 2, "advanced": 2}


def grade_label(grade: Any) -> str:
    return GRADE_LABELS.get(grade, f"{grade}年级" if grade else "")


def is_math_topic(topic: Dict[str, Any]) -> bool:
    """pansgo 数据里数学知识点的 subject 是 null（不是 "math"）。"""
    return topic.get("subject") in (None, "", "math")


def in_scope(topic: Dict[str, Any], max_grade: int = MAX_GRADE) -> bool:
    """是否属于数学 1–max_grade 年级的正式知识点。"""
    if not is_math_topic(topic) or topic.get("external") is True:
        return False
    grade = topic.get("grade")
    return isinstance(grade, int) and 1 <= grade <= max_grade


def filter_math(
    topics: Iterable[Dict[str, Any]],
    dependencies: Iterable[Dict[str, Any]],
    questions: Iterable[Dict[str, Any]],
    max_grade: int = MAX_GRADE,
) -> Dict[str, List[Dict[str, Any]]]:
    """按数学 + 年级 + 非外部节点过滤，并只保留两端都在范围内的先修边。"""
    kept_topics = [t for t in topics if in_scope(t, max_grade)]
    ids = {t["id"] for t in kept_topics}
    kept_deps = [
        d
        for d in dependencies
        if d.get("topicId") in ids and d.get("prerequisiteId") in ids
    ]
    kept_questions = [q for q in questions if q.get("topicId") in ids]
    return {
        "topics": kept_topics,
        "dependencies": kept_deps,
        "questions": kept_questions,
    }


def validate(filtered: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """校验引用完整性、重复 id、自环与空题，返回错误列表（空表示通过）。"""
    errors: List[str] = []
    topics = filtered["topics"]
    deps = filtered["dependencies"]
    questions = filtered["questions"]

    ids = [t.get("id") for t in topics]
    if len(ids) != len(set(ids)):
        errors.append("知识点 id 存在重复")
    id_set = set(ids)

    for d in deps:
        src, dst = d.get("prerequisiteId"), d.get("topicId")
        if src not in id_set or dst not in id_set:
            errors.append(f"先修边端点不在范围内: {src} -> {dst}")
        if src == dst:
            errors.append(f"先修边存在自环: {src}")

    qids = [q.get("id") for q in questions]
    if len(qids) != len(set(qids)):
        errors.append("题目 id 存在重复")
    for q in questions:
        if q.get("topicId") not in id_set:
            errors.append(f"题目 {q.get('id')} 指向未知知识点 {q.get('topicId')}")
        for key in ("prompt", "answer"):
            if q.get(key) in (None, ""):
                errors.append(f"题目 {q.get('id')} 缺少 {key}")
    return errors


def build_graph(
    topics: List[Dict[str, Any]],
    dependencies: List[Dict[str, Any]],
    max_grade: int = MAX_GRADE,
) -> Dict[str, Any]:
    """转成项目现有图谱 JSON 格式（nodes + edges）。

    边方向与 K12-KGraph 一致：source 是先学节点，target 是后学节点。
    pansgo 的 dependencies 里 topicId 依赖 prerequisiteId，故 source=prerequisiteId。
    """
    name_by_id = {t["id"]: t.get("name") for t in topics}
    nodes = [_topic_to_node(t) for t in sorted(topics, key=_topic_sort_key)]
    edges = [
        _dependency_to_edge(d, name_by_id)
        for d in sorted(dependencies, key=lambda x: (x.get("prerequisiteId", ""), x.get("topicId", "")))
    ]
    return {
        "book_id": DATASET_ID,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "dataset": DATASET_ID,
            "subject": "math",
            "grades": [1, max_grade],
            "source_repo": SOURCE_REPO,
            "source_site": SOURCE_SITE,
            "source_commit": SOURCE_COMMIT,
            "license": LICENSE,
            "license_url": LICENSE_URL,
            "attribution": ATTRIBUTION,
            "note": "题目与知识点由 cn-math-taxonomy 的 AI 生成流程产出，未经一线教师审核。",
        },
    }


def build_question_bank(questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """转成题库 JSON（保留判题所需字段，按 topicId + id 稳定排序）。"""
    cleaned = [_clean_question(q) for q in questions]
    cleaned.sort(key=lambda q: (q.get("topicId", ""), q.get("id", "")))
    return {
        "dataset": DATASET_ID,
        "source_repo": SOURCE_REPO,
        "source_commit": SOURCE_COMMIT,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "attribution": ATTRIBUTION,
        "count": len(cleaned),
        "questions": cleaned,
    }


def _topic_to_node(topic: Dict[str, Any]) -> Dict[str, Any]:
    grade = topic.get("grade")
    chapter = topic.get("chapter") or ""
    book = _book_of(chapter, grade)
    props = {
        "grade": grade,
        "grade_label": grade_label(grade),
        "stage": GRADE_STAGES.get(grade, ""),
        "semester": topic.get("semester"),
        "book": book,
        "chapter": chapter,
        "chapter_label": _chapter_label(chapter, book),
        "domain": topic.get("domain"),
        "topic_type": topic.get("type"),
        "description": topic.get("description"),
        "mastery_criteria": topic.get("mastery_criteria") or [],
        "standards": topic.get("standards") or [],
        "diagnostic_question": topic.get("diagnostic_question"),
        "source": PRODUCER,
    }
    return {
        "id": topic["id"],
        "label": NODE_LABEL,
        "name": topic.get("name") or topic["id"],
        "properties": _compact(props),
    }


def _dependency_to_edge(
    dep: Dict[str, Any], name_by_id: Dict[str, Any]
) -> Dict[str, Any]:
    props = {
        "strength": dep.get("strength"),
        "reason": dep.get("reason"),
        "source": PRODUCER,
    }
    return {
        "source": dep["prerequisiteId"],
        "source_name": name_by_id.get(dep["prerequisiteId"]),
        "target": dep["topicId"],
        "target_name": name_by_id.get(dep["topicId"]),
        "type": PREREQ_EDGE_TYPE,
        "properties": _compact(props),
    }


def _clean_question(q: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": q.get("id"),
        "topicId": q.get("topicId"),
        "difficulty": q.get("difficulty"),
        "type": q.get("type"),
        "prompt": q.get("prompt"),
        "answer": q.get("answer"),
    }
    for key in ("explanation", "verify", "figure"):
        if q.get(key):
            out[key] = q[key]
    if q.get("choices"):
        out["choices"] = [
            {"key": c.get("key"), "text": c.get("text")}
            | ({"figure": c["figure"]} if c.get("figure") else {})
            for c in q["choices"]
        ]
    if q.get("accept"):
        out["accept"] = q["accept"]
    if q.get("unordered"):
        out["unordered"] = True
    if q.get("hideChoiceText"):
        out["hideChoiceText"] = True
    return out


def _topic_sort_key(topic: Dict[str, Any]) -> Tuple[int, str]:
    return (topic.get("grade") or 0, topic.get("id") or "")


def _compact(props: Dict[str, Any]) -> Dict[str, Any]:
    """去掉 None 与空字符串，避免 properties_json 里堆无用键。"""
    return {k: v for k, v in props.items() if v not in (None, "")}


def build_catalog(
    topics: List[Dict[str, Any]], questions: Iterable[Dict[str, Any]] | None = None
) -> Dict[str, Any]:
    """构建前端选范围用的目录：年级 → 册 → 章 → 知识点。

    保持源数据的先后顺序（章节顺序以 topics.json 为准），不按字符串重排，
    避免「第十章」排在「第二章」前面。
    """
    qcount: Dict[str, int] = {}
    for q in questions or ():
        topic_id = q.get("topicId")
        if topic_id:
            qcount[topic_id] = qcount.get(topic_id, 0) + 1

    grades: Dict[int, Dict[str, Any]] = {}
    books: Dict[tuple, Dict[str, Any]] = {}
    catalog_topics: List[Dict[str, Any]] = []

    for topic in topics:
        grade = topic.get("grade")
        if not isinstance(grade, int):
            continue
        chapter = (topic.get("chapter") or "").strip()
        book = _book_of(chapter, grade)
        chapter_label = _chapter_label(chapter, book)
        semester = topic.get("semester") or ""
        topic_id = topic["id"]

        grade_entry = grades.setdefault(
            grade,
            {
                "grade": grade,
                "label": grade_label(grade),
                "stage": GRADE_STAGES.get(grade, ""),
                "topic_count": 0,
                "question_count": 0,
                "_semesters": set(),
            },
        )
        book_entry = books.setdefault(
            (grade, book),
            {
                "book": book,
                "grade": grade,
                "grade_label": grade_label(grade),
                "stage": GRADE_STAGES.get(grade, ""),
                "semester": semester,
                "topic_count": 0,
                "question_count": 0,
                "chapters": {},
            },
        )
        chapter_entry = book_entry["chapters"].setdefault(
            chapter,
            {
                "chapter": chapter,
                "label": chapter_label,
                "topic_count": 0,
                "question_count": 0,
                "node_ids": [],
            },
        )

        qn = qcount.get(topic_id, 0)
        grade_entry["topic_count"] += 1
        grade_entry["question_count"] += qn
        grade_entry["_semesters"].add(semester)
        book_entry["topic_count"] += 1
        book_entry["question_count"] += qn
        chapter_entry["topic_count"] += 1
        chapter_entry["question_count"] += qn
        chapter_entry["node_ids"].append(topic_id)

        catalog_topics.append(
            {
                "id": topic_id,
                "name": topic.get("name") or topic_id,
                "grade": grade,
                "grade_label": grade_label(grade),
                "stage": GRADE_STAGES.get(grade, ""),
                "semester": semester,
                "book": book,
                "chapter": chapter,
                "chapter_label": chapter_label,
                "question_count": qn,
            }
        )

    grade_list: List[Dict[str, Any]] = []
    for grade in sorted(grades):
        entry = grades[grade]
        entry["semesters"] = sorted(entry.pop("_semesters"), key=_semester_order)
        entry["books"] = [b for (g, _), b in books.items() if g == grade]
        for book_entry in entry["books"]:
            book_entry["chapters"] = list(book_entry["chapters"].values())
        entry["book_count"] = len(entry["books"])
        grade_list.append(entry)

    return {
        "dataset": DATASET_ID,
        "source_commit": SOURCE_COMMIT,
        "license": LICENSE,
        "grades": grade_list,
        "topics": catalog_topics,
        "topic_count": len(catalog_topics),
    }


def _book_of(chapter: str, grade: int) -> str:
    """章节字符串的第一个空格前是册次：一年级上册 / 七上 / 高一 / 选必一。"""
    if chapter and " " in chapter:
        return chapter.split(" ", 1)[0]
    return chapter or grade_label(grade)


def _chapter_label(chapter: str, book: str) -> str:
    if chapter.startswith(book):
        label = chapter[len(book):].strip()
        return label or chapter
    return chapter


def _semester_order(semester: str) -> int:
    return {"上": 0, "下": 1}.get(semester, 2)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload: Any) -> str:
    """以 UTF-8 稳定格式写 JSON，返回内容 sha256（用于幂等导入与溯源）。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    data = (text + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data)


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
