"""从五年级下册知识点出发抽取子图，作为图谱构建（实验 4）的输入。

抽取策略（保持子图自包含，只含人教版五年级下册内容）：
- 节点 = 59 个知识点（Concept + Skill）∪ 它们归属的本册章节（Chapter）；
- 边 = 知识点之间的结构关系（prerequisites_for / is_a / relates_to，两端均在种子内）
      + 知识点到本册章节的 appears_in 归属边。

跨册的边（低年级前置、同主题延伸等）一律不纳入。这些边对「前置知识诊断」
有价值，留待后续步骤按需扩展。
"""

import collections
import json
from pathlib import Path
from typing import List, Set, Tuple

from .filter import build_book_knowledge_points
from .loader import load_edges, load_nodes
from .models import Edge, Node

# 知识点之间的结构关系（两端均为知识点）
INTERNAL_EDGE_TYPES = frozenset({"prerequisites_for", "is_a", "relates_to"})
# 知识点到章节的归属关系（用于答案溯源）
ATTACH_EDGE_TYPES = frozenset({"appears_in"})
# 章节/教材结构节点类型（appears_in 的合法目标）
CHAPTER_NODE_LABELS = frozenset({"Chapter", "Section"})

ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "math.json"
OUT_PATH = ROOT / "data" / "processed" / "math_5b_knowledge_graph.json"
BOOK_ID = "math_5b_rjb"


def extract_subgraph(
    nodes: List[Node],
    edges: List[Edge],
    seed_ids: Set[str],
    book_id: str,
) -> Tuple[List[Node], List[Edge]]:
    """抽取种子知识点的子图。

    保留规则：
    - 内部边（prerequisites_for / is_a / relates_to）：source、target 都在种子内；
    - 归属边（appears_in）：source 在种子内，且 target 是指定教材册下的章节节点；
    - 结果节点 = 种子 ∪ 被保留归属边引出的章节。

    返回 (节点, 边)，均按 id/(source, target, type) 排序，输出确定。
    """
    seed = set(seed_ids)
    node_by_id = {n.id: n for n in nodes}
    prefix = book_id + "_"

    kept_edges: List[Edge] = []
    for e in edges:
        if e.type in INTERNAL_EDGE_TYPES:
            if e.source in seed and e.target in seed:
                kept_edges.append(e)
        elif e.type in ATTACH_EDGE_TYPES:
            target = node_by_id.get(e.target)
            if (
                e.source in seed
                and target is not None
                and target.id.startswith(prefix)
                and target.label in CHAPTER_NODE_LABELS
            ):
                kept_edges.append(e)

    kept_ids = set(seed)
    for e in kept_edges:
        kept_ids.add(e.source)
        kept_ids.add(e.target)

    kept_nodes = sorted(
        (node_by_id[i] for i in kept_ids if i in node_by_id), key=lambda n: n.id
    )
    kept_edges = sorted(kept_edges, key=lambda e: (e.source, e.target, e.type))
    return kept_nodes, kept_edges


def _node_to_dict(n: Node) -> dict:
    return {"id": n.id, "label": n.label, "name": n.name, "properties": n.properties}


def _edge_to_dict(e: Edge) -> dict:
    return {"source": e.source, "target": e.target, "type": e.type, "properties": e.properties}


def build_math_5b_subgraph(
    raw_path: Path = RAW_PATH, out_path: Path = OUT_PATH
) -> Tuple[List[Node], List[Edge]]:
    """加载数学图谱 → 取五年级下册知识点 → 抽取子图 → 写 JSON。"""
    nodes = load_nodes(raw_path)
    edges = load_edges(raw_path)
    seed = [n.id for n in build_book_knowledge_points(nodes, BOOK_ID)]
    sub_nodes, sub_edges = extract_subgraph(nodes, edges, set(seed), BOOK_ID)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "book_id": BOOK_ID,
        "node_count": len(sub_nodes),
        "edge_count": len(sub_edges),
        "nodes": [_node_to_dict(n) for n in sub_nodes],
        "edges": [_edge_to_dict(e) for e in sub_edges],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return sub_nodes, sub_edges


if __name__ == "__main__":
    sub_nodes, sub_edges = build_math_5b_subgraph()
    labels = dict(collections.Counter(n.label for n in sub_nodes))
    etypes = dict(collections.Counter(e.type for e in sub_edges))
    print(f"子图写出: {OUT_PATH}")
    print(f"节点 {len(sub_nodes)} 个: {labels}")
    print(f"边 {len(sub_edges)} 条: {etypes}")
