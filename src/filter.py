"""按年级与重要性筛选知识点（服务于「知识点 ≤ 200」的规模约束）。

筛选策略（两步）：
1. 按年级：只保留某一教材册（如人教版五年级下册 `math_5b_rjb`）下的节点；
2. 按重要性：对知识点（Concept + Skill）按 importance 排序，截取前 limit 个。

注意：
- 只有 Concept 有 importance 字段，Skill 无该字段，故 Skill 统一排在最后；
- 数据集中 importance 出现「重要」这类非常规取值（标准层次为 了解/理解/掌握/应用），
  属标注噪声；按其覆盖内容（通分/约分/分数的基本性质等核心点）暂与「掌握」同级，
  具体映射见 IMPORTANCE_RANK。
"""

from typing import List

from .models import KNOWLEDGE_LABELS, Node

# importance 认知层次（高 → 低），数字越大越优先。
# 依据课程目标分类：应用/运用 > 掌握 > 理解 > 了解。
# 「重要」等未收录取值按 0（最低）处理，详见模块注释。
IMPORTANCE_RANK = {
    "应用": 4,
    "运用": 4,
    "掌握": 3,
    # 「重要」并非标准认知层次，属标注噪声；据其覆盖内容（通分/约分/分数的基本性质等
    # 核心知识点）暂与「掌握」同级处理——此假设需人工确认。
    "重要": 3,
    "理解": 2,
    "了解": 1,
}

# 项目规模约束：知识点上限
DEFAULT_KNOWLEDGE_LIMIT = 200


def filter_by_book(nodes: List[Node], book_id: str) -> List[Node]:
    """按教材册筛选：id 以 `{book_id}_` 为前缀的节点属于该册。

    例如 book_id=`math_5b_rjb` 会命中 `math_5b_rjb_cpt1` 等，
    而不会命中 Book 自身（其 id 恰为 `math_5b_rjb`，无下划线后缀）。
    """
    prefix = book_id + "_"
    return [n for n in nodes if n.id.startswith(prefix)]


def _importance_rank(node: Node) -> int:
    """节点的 importance 排名；Skill 或无 importance 的节点排最低档。"""
    level = node.properties.get("importance")
    return IMPORTANCE_RANK.get(level, 0)


def select_knowledge_points(
    nodes: List[Node], limit: int = DEFAULT_KNOWLEDGE_LIMIT
) -> List[Node]:
    """从节点中选出知识点（Concept + Skill），按 importance 降序，截取前 limit 个。

    排序稳定：同档 importance 内保持原始顺序。
    """
    kps = [n for n in nodes if n.label in KNOWLEDGE_LABELS]
    kps.sort(key=_importance_rank, reverse=True)
    return kps[:limit]


def build_book_knowledge_points(
    nodes: List[Node], book_id: str, limit: int = DEFAULT_KNOWLEDGE_LIMIT
) -> List[Node]:
    """组合两步：先按年级筛选到某教材册，再按 importance 选出 ≤ limit 个知识点。"""
    return select_knowledge_points(filter_by_book(nodes, book_id), limit)
