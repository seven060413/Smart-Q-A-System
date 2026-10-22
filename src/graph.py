"""实验 4 · 图谱构建：用 NetworkX 建模五年级下册知识子图，
判定前置关系的性质（传递性、环），为学习路径生成提供基础。

前置边方向约定：`source → target` 表示 source 是 target 的前置（先学 source，再学 target）。
因此求某知识点的全部前置（含间接）等价于求「祖先」（nx.ancestors）。
"""

import json
from pathlib import Path
from typing import Dict, List, Set

import networkx as nx

from .loader import load_edges, load_nodes
from .models import Edge, Node
from .subgraph import OUT_PATH, RAW_PATH

# 前置关系类型
PREREQ = "prerequisites_for"


def build_digraph(nodes: List[Node], edges: List[Edge]) -> nx.MultiDiGraph:
    """由节点与边构建有向图；边方向 source → target。

    K12-KGraph 是多关系图谱：同一对节点之间可能存在多条不同类型的关系边
    （如「最少称量次数 → 物品数量与最少称量次数的关系」同时有 prerequisites_for
    与 relates_to）。故用 MultiDiGraph 保留全部关系，避免后写入的类型覆盖先写入的。
    """
    g = nx.MultiDiGraph()
    for n in nodes:
        g.add_node(n.id, label=n.label, name=n.name, properties=n.properties)
    for e in edges:
        g.add_edge(e.source, e.target, type=e.type, properties=e.properties)
    return g


def prerequisite_graph(g: nx.MultiDiGraph) -> nx.DiGraph:
    """只保留前置边的简单有向子图（含全部节点）。

    前置边在同一对节点间至多一条，降为简单 DiGraph 便于环检测与拓扑排序；
    g.edges(data=True) 会遍历多重图中的全部平行边，故不会漏掉被其他关系「遮盖」的前置边。
    """
    sub = nx.DiGraph()
    sub.add_nodes_from(g.nodes(data=True))
    for u, v, d in g.edges(data=True):
        if d.get("type") == PREREQ:
            sub.add_edge(u, v)
    return sub


def indirect_prerequisites(g: nx.DiGraph, node_id: str) -> Set[str]:
    """node_id 的全部前置（含间接前置）：能沿前置边到达它的节点集合。"""
    return set(nx.ancestors(g, node_id)) if node_id in g else set()


def find_cycles(g: nx.DiGraph) -> List[List[str]]:
    """找出前置关系图中的所有简单环；每个环返回闭环节点序列 [n1, n2, ..., nk, n1]。"""
    return [cyc + [cyc[0]] for cyc in nx.simple_cycles(g)]


def check_prereq_properties(g: nx.DiGraph) -> Dict:
    """判定前置关系的性质。

    若既无自环也无环，则前置关系是合法的偏序（非自反、反对称、无环），
    可用拓扑排序生成学习路径；否则报告自环与环的完整序列。
    """
    self_loops = [n for n in g.nodes() if g.has_edge(n, n)]
    cycles = find_cycles(g)
    return {
        "node_count": g.number_of_nodes(),
        "edge_count": g.number_of_edges(),
        "self_loops": self_loops,
        "cycles": cycles,
        "is_acyclic": not self_loops and not cycles,
    }


def topological_order(g: nx.DiGraph) -> List[str]:
    """前置图的拓扑序（一种合法学习顺序）；存在环时抛出 NetworkXUnfeasible。"""
    return list(nx.topological_sort(g))


def neighbor_subgraph(g, seed_ids, radius: int = 1) -> nx.DiGraph:
    """相邻子图查询：取种子节点 radius 跳内的诱导子图。"""
    seeds = [s for s in seed_ids if s in g]
    if not seeds:
        return nx.DiGraph()
    nodes = set()
    for s in seeds:
        nodes.update(nx.ego_graph(g, s, radius=radius).nodes())
    return g.subgraph(nodes).copy()


def has_path(g, source, target) -> bool:
    """连通性判定：source 能否沿有向边到达 target。"""
    return nx.has_path(g, source, target)


def shortest_path(g, source, target) -> List[str]:
    """路径查询：source → target 的最短路径（不存在返回空列表）。"""
    if not has_path(g, source, target):
        return []
    return nx.shortest_path(g, source, target)


def weakly_connected_components(g) -> List[List[str]]:
    """连通分量（忽略方向）：用于整体结构判定。"""
    return [list(c) for c in nx.weakly_connected_components(g)]


def citing_chapters(g, node_id) -> List[str]:
    """溯源：返回 node_id 通过 appears_in 归属的章节节点 id 列表。"""
    chapters = []
    for e in g.out_edges(node_id, data=True):
        v, d = e[1], e[-1]      # 兼容 (u,v,data) 与 (u,v,key,data) 两种元组形态
        if d.get("type") == "appears_in":
            chapters.append(v)
    return chapters


def load_full_graph(path: Path = RAW_PATH) -> nx.MultiDiGraph:
    """从 data/raw/math.json 构建全量数学图谱（含跨册前置，供前置诊断用）。"""
    return build_digraph(load_nodes(path), load_edges(path))


def load_5b_graph(path: Path = OUT_PATH) -> nx.DiGraph:
    """从 data/processed 的子图 JSON 直接构建五年级下册知识图谱。"""
    return build_digraph(load_nodes(path), load_edges(path))


if __name__ == "__main__":
    g = load_5b_graph()
    pg = prerequisite_graph(g)
    report = check_prereq_properties(pg)
    print("五年级下册前置关系性质判定：")
    print(f"  节点 {report['node_count']} 个，前置边 {report['edge_count']} 条")
    print(f"  自环: {report['self_loops']}")
    print(f"  环: {report['cycles']}")
    print(f"  无环（可生成学习路径）: {report['is_acyclic']}")
