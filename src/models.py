"""实验 1 · 集合建模：三个有限集合的数据模型。

把 K12-KGraph 数学图谱的节点组织成三个有限集合（映射到真实数据）：

- 实体集合   E：全部 6 类节点 Book / Chapter / Section / Concept / Skill / Exercise
- 知识点集合 K：Concept 与 Skill 两类节点（教与学的目标内容）
- 教材章节集合 C：Chapter 与 Section 两类节点（教材结构，用于答案溯源）

三者满足：K ⊆ E，C ⊆ E，K ∩ C = ∅（知识点与章节语义上互不相交）。

建模依据：
1. 数据集中节点用 `label` 字段区分类型，每个节点恰好属于一种类型，
   因此以 label 为划分依据可得到边界清晰、有限且可枚举的集合。
2. 「知识点」对应 Concept（概念）与 Skill（技能），是问答系统的核心对象；
   「章节」对应 Chapter（章/单元）与 Section（节），是答案出处的结构载体；
   二者语义不相交，故 K ∩ C = ∅。
3. 「实体」是图谱中的一切节点，为其余两个集合的全集，故 K、C 均为 E 的子集。

注意：数学全量图谱含 1470 个 Concept 与 428 个 Skill，共 1898 个知识点，
超出项目「知识点 ≤ 200」的规模约束；后续步骤需按年级/教材筛选出 ≤200 的子集。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

# 实体集合 E 覆盖的 6 种节点类型
ENTITY_LABELS = frozenset({"Book", "Chapter", "Section", "Concept", "Skill", "Exercise"})
# 知识点集合 K 的节点类型
KNOWLEDGE_LABELS = frozenset({"Concept", "Skill"})
# 教材章节集合 C 的节点类型
CHAPTER_LABELS = frozenset({"Chapter", "Section"})


@dataclass
class Node:
    """图谱节点（实体）。"""
    id: str
    label: str
    name: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    """图谱边（关系），source/target 为节点 id。"""
    source: str
    target: str
    type: str
    properties: Dict[str, Any] = field(default_factory=dict)


class GraphSets:
    """把一组节点组织成三个有限集合。

    集合元素用节点 id（str）表示；节点本体可用 node() 查询。
    """

    def __init__(self, nodes: List[Node]):
        self._nodes: Dict[str, Node] = {n.id: n for n in nodes}

    def node(self, node_id: str) -> Node:
        """按 id 取节点。"""
        return self._nodes[node_id]

    @property
    def entity_set(self) -> Set[str]:
        """实体集合 E：全部节点 id。"""
        return set(self._nodes.keys())

    @property
    def knowledge_point_set(self) -> Set[str]:
        """知识点集合 K：Concept 与 Skill 节点的 id。"""
        return {nid for nid, n in self._nodes.items() if n.label in KNOWLEDGE_LABELS}

    @property
    def chapter_set(self) -> Set[str]:
        """教材章节集合 C：Chapter 与 Section 节点的 id。"""
        return {nid for nid, n in self._nodes.items() if n.label in CHAPTER_LABELS}

    def knowledge_points(self) -> List[Node]:
        """知识点集合中的节点本体（用于查看属性）。"""
        return [n for n in self._nodes.values() if n.label in KNOWLEDGE_LABELS]

    def chapters(self) -> List[Node]:
        """教材章节集合中的节点本体（用于查看属性）。"""
        return [n for n in self._nodes.values() if n.label in CHAPTER_LABELS]
