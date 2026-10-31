"""前置知识诊断（实验 3 谓词逻辑）。

两类量词查询：
1. 前置回溯：给定知识点 X，存在哪些知识点 y 是 X 的前置 —— ∃y: y 前置 X；
2. 反向查询：给定知识点 X，存在哪些知识点 y 以 X 为前置 —— ∃y: X 前置 y。

诊断输出：定位本体 → 回溯前置链 → 输出知识缺口。
必需/建议判定依据：
- 直接前置（1 跳）＝必需：没有它无法直接理解本体；
- 间接前置（≥2 跳）＝建议：更基础但离本体较远，可先补。
"""

from __future__ import annotations

import re
from typing import Dict, List

import networkx as nx

from .graph import citing_chapters, indirect_prerequisites, prerequisite_graph

# 找不到教材归属时的兜底出处
FALLBACK_CITATION = "知识图谱"


def _book_of(g, node_id: str) -> str | None:
    """沿 is_part_of 向上找到所属教材 Book 节点。"""
    current = node_id
    seen = set()
    while current and current not in seen:
        seen.add(current)
        if current not in g:
            return None
        if g.nodes[current].get("label") == "Book":
            return current
        next_id = None
        for e in g.out_edges(current, data=True):
            target, data = e[1], e[-1]
            if data.get("type") != "is_part_of" or target not in g:
                continue
            if g.nodes[target].get("label") in ("Book", "Chapter", "Section"):
                next_id = target
                break
        current = next_id
    return None


def _book_label(g, book_id: str) -> str:
    """教材显示名，如「人教版五年级下册」。

    Book.properties.publisher 在部分高中教材里是完整的长串
    （如「人教版（A版）（主编：…）-人民教育出版社」），这里取出版社主体，
    避免出处过长。
    """
    props = g.nodes[book_id].get("properties", {}) or {}
    publisher = (props.get("publisher") or "").strip()
    publisher = re.split(r"[（(]|[-—]", publisher)[0].strip() or publisher
    grade = (props.get("grade") or "").strip()
    if publisher and grade:
        return f"{publisher}{grade}"
    return (g.nodes[book_id].get("name") or "").strip()


def prerequisites_of(g, node_id: str) -> List[str]:
    """量词查询：node_id 的全部前置（含间接）。"""
    return sorted(indirect_prerequisites(prerequisite_graph(g), node_id))


def dependents_of(g, node_id: str) -> List[str]:
    """量词查询：以 node_id 为前置的全部知识点（含间接）。"""
    return sorted(nx.descendants(prerequisite_graph(g), node_id))


def diagnose(g, node_id: str) -> Dict:
    """前置诊断：返回 {body, required(必需), suggested(建议)}。"""
    pg = prerequisite_graph(g)
    direct = sorted(pg.predecessors(node_id)) if node_id in pg else []
    all_prereq = sorted(indirect_prerequisites(pg, node_id))
    suggested = [p for p in all_prereq if p not in direct]
    return {"body": node_id, "required": direct, "suggested": suggested}


def format_citation(g, node_id: str) -> str:
    """返回答案出处，如「人教版五年级下册·分数的加法和减法」。

    全量图谱下不再固定为五年级下册，而是沿 appears_in → is_part_of 找到
    知识点实际所属的教材和章节；找不到时回退为「知识图谱」。
    """
    chapter_names: List[str] = []
    book_labels: List[str] = []
    for chapter_id in citing_chapters(g, node_id):
        if chapter_id not in g:
            continue
        chapter_name = g.nodes[chapter_id].get("name")
        if chapter_name and chapter_name not in chapter_names:
            chapter_names.append(chapter_name)
        book_id = _book_of(g, chapter_id)
        if book_id:
            label = _book_label(g, book_id)
            if label and label not in book_labels:
                book_labels.append(label)

    parts = []
    if book_labels:
        parts.append("、".join(book_labels))
    if chapter_names:
        parts.append("、".join(chapter_names))
    return "·".join(parts) if parts else FALLBACK_CITATION
