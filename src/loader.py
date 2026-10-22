"""从 data/raw/math.json 加载数学图谱。"""

import json
from pathlib import Path
from typing import List, Union

from .models import Edge, Node


def load_nodes(path: Union[str, Path]) -> List[Node]:
    """读取 math.json，返回其中的全部节点（实体集合的原始数据）。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [
        Node(
            id=n["id"],
            label=n["label"],
            name=n["name"],
            properties=n.get("properties", {}),
        )
        for n in data["nodes"]
    ]


def load_edges(path: Union[str, Path]) -> List[Edge]:
    """读取 math.json 的边，仅返回含标量 target 的标准边。

    tests_concept / tests_skill 的 target 是 target_name_to_ids 列表（一题多知识点），
    结构特殊，留待习题/评测步骤单独处理，此处跳过。
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    edges = []
    for e in data["edges"]:
        if "target" not in e:
            continue
        edges.append(Edge(
            source=e["source"],
            target=e["target"],
            type=e["type"],
            properties=e.get("properties", {}),
        ))
    return edges
