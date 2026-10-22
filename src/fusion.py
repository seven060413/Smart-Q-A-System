"""双通道检索融合。

融合规则（教师要求「融合规则要有依据」）：
- 文本通道得分 text_score：余弦相似度，天然归一化到 [0,1]；
- 图谱通道得分 graph_score：节点是否落在锚点的前置链或相邻子图内（命中 1.0，否则 0）；
- 加权求和：final = 0.7 * text_score + 0.3 * graph_score。

权重依据：
1. 语义相关性是问答的第一证据——用户问的是「内容」，故文本通道权重更高（0.7）；
2. 图谱结构是第二证据——前置/邻近关系用于补全学生缺的前置知识，但不改变主答案，
   故权重较低（0.3）；
3. 两个通道必须归一化到同一量纲 [0,1] 才能直接加权，否则量纲差异会扭曲权重含义。
"""

from typing import Dict, List, Set, Tuple

from .graph import indirect_prerequisites, neighbor_subgraph, prerequisite_graph


def fuse(
    text_hits: Dict[str, float],
    graph_hits: Dict[str, float],
    alpha: float = 0.7,
) -> List[Tuple[str, float]]:
    """融合两通道命中，返回按 final 降序的 [(node_id, final_score)]。"""
    ids: Set[str] = set(text_hits) | set(graph_hits)
    merged = [
        (
            nid,
            alpha * text_hits.get(nid, 0.0) + (1 - alpha) * graph_hits.get(nid, 0.0),
        )
        for nid in ids
    ]
    merged.sort(key=lambda x: x[1], reverse=True)
    return merged


def graph_channel_hits(g, anchor_id: str) -> Dict[str, float]:
    """图谱通道：返回锚点的前置链 ∪ 相邻子图 的知识点（排除锚点自身与章节节点）。"""
    hits: Dict[str, float] = {}
    if anchor_id not in g:
        return hits
    pg = prerequisite_graph(g)
    for nid in indirect_prerequisites(pg, anchor_id):
        hits[nid] = 1.0
    for nid in neighbor_subgraph(g, {anchor_id}, radius=1).nodes():
        if g.nodes[nid].get("label") in ("Concept", "Skill"):
            hits.setdefault(nid, 1.0)
    hits.pop(anchor_id, None)
    return hits


def dual_retrieve(question, nodes, g, text_retriever, top_k: int = 5) -> Dict:
    """双通道检索编排：实体链接 → 文本通道 + 图谱通道 → 融合。"""
    from .linking import link_entity

    anchors = link_entity(question, nodes, top_k=1)
    anchor = anchors[0][0] if anchors else None

    text_hits = dict(text_retriever.retrieve(question, k=top_k))
    graph_hits = graph_channel_hits(g, anchor.id) if anchor is not None else {}
    ranked = fuse(text_hits, graph_hits)

    prereqs: List[str] = []
    if anchor is not None:
        prereqs = sorted(indirect_prerequisites(prerequisite_graph(g), anchor.id))

    return {
        "anchor": anchor.id if anchor is not None else None,
        "ranked": ranked,
        "prerequisites": prereqs,
    }
