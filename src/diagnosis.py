"""前置知识诊断（实验 3 谓词逻辑）。

两类量词查询：
1. 前置回溯：给定知识点 X，存在哪些知识点 y 是 X 的前置 —— ∃y: y 前置 X；
2. 反向查询：给定知识点 X，存在哪些知识点 y 以 X 为前置 —— ∃y: X 前置 y。

诊断输出：定位本体 → 回溯前置链 → 输出知识缺口。
必需/建议判定依据：
- 直接前置（1 跳）＝必需：没有它无法直接理解本体；
- 间接前置（≥2 跳）＝建议：更基础但离本体较远，可先补。
"""

from typing import Dict, List

import networkx as nx

from .graph import citing_chapters, indirect_prerequisites, prerequisite_graph

# 当前系统仅覆盖人教版五年级下册
BOOK_CITATION = "人教版五年级下册"


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
    """返回答案出处，如「人教版五年级下册·分数的加法和减法」。"""
    chapters = citing_chapters(g, node_id)
    names = [g.nodes[c]["name"] for c in chapters if c in g]
    if not names:
        return BOOK_CITATION
    return "·".join([BOOK_CITATION] + names)
