"""学习路径生成（实验 8 树）。

按图谱拓扑生成「前置—本体—巩固」三级路径：
- 前置层：本体的前置链（按拓扑序，基础在前）；
- 本体层：本体自身；
- 巩固层：以本体为前置的后继 ∪ relates_to 邻居（学了本体后接着练/学什么）。

前置链成环时禁止生成路径：先检测环，有环抛 ValueError 并输出完整闭环序列（杀手用例）。
"""

from typing import Dict, List

import networkx as nx

from .graph import find_cycles, indirect_prerequisites, prerequisite_graph


def _consolidation(g, pg, body_id: str) -> List[str]:
    """巩固层 = 以本体为前置的后继 ∪ relates_to 出邻居。"""
    result = set(nx.descendants(pg, body_id))
    for e in g.out_edges(body_id, data=True):
        v, d = e[1], e[-1]
        if d.get("type") == "relates_to":
            result.add(v)
    return sorted(result)


def build_learning_path(g, body_id: str) -> Dict:
    """生成三级学习路径；前置链有环则报错并输出环序列。"""
    pg = prerequisite_graph(g)

    # 环检测：前置链（含本体）内成环 → 禁止生成路径
    if body_id in pg:
        scope = set(indirect_prerequisites(pg, body_id)) | {body_id}
        cycles = find_cycles(pg.subgraph(scope))
        if cycles:
            raise ValueError(f"前置关系存在环，无法生成学习路径：{cycles}")

    prereq = list(indirect_prerequisites(pg, body_id))
    if prereq:
        order = {
            n: i
            for i, n in enumerate(nx.topological_sort(pg.subgraph(set(prereq) | {body_id})))
        }
        prereq.sort(key=lambda n: order.get(n, len(order)))

    return {
        "prerequisites": prereq,
        "body": body_id,
        "consolidation": _consolidation(g, pg, body_id),
    }


def format_path_tree(path: Dict, g) -> str:
    """把三级路径渲染成树形文本（用于展示/答辩）。"""
    def name(nid):
        return g.nodes[nid].get("name", nid)

    lines = [name(path["body"]) + "（本体）"]
    if path["prerequisites"]:
        lines.append("├─ 前置：" + "、".join(name(p) for p in path["prerequisites"]))
    if path["consolidation"]:
        lines.append("└─ 巩固：" + "、".join(name(c) for c in path["consolidation"]))
    return "\n".join(lines)
