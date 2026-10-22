"""拒答：知识库未覆盖的问题明确拒答，并给出最接近的已覆盖知识点。

依据（溯源/拒答 功能 6）：
- 实体链接分数低于阈值 → 判定「知识库未覆盖」，拒绝回答、绝不猜测；
- 返回链接分数最高的知识点作为「最接近」提示。
"""

from typing import Dict, Tuple

from .linking import link_entity
from .models import Node

# 链接分数阈值：低于该值视为知识库未覆盖。
# 依据：库内问句最高分约 0.49+（如「异分母分数通分」）；仅靠单字偶然重叠的
# 库外问句约 0.15（如「导数」只命中「倍数/奇数」里的「数」字）。取 0.2 居中。
LINK_THRESHOLD = 0.2


def link_top(question: str, nodes) -> Tuple:
    """返回链接最高的 (node, score)；无候选返回 (None, 0.0)。"""
    hits = link_entity(question, nodes, top_k=1)
    return (hits[0][0], hits[0][1]) if hits else (None, 0.0)


def is_covered(question: str, nodes) -> bool:
    """判断问题是否被知识库覆盖（链接分数达到阈值）。"""
    _, score = link_top(question, nodes)
    return score >= LINK_THRESHOLD


def refusal_message(question: str, nodes) -> Dict:
    """库外问题返回拒答信息（含最接近知识点）。"""
    node, _ = link_top(question, nodes)
    return {
        "covered": False,
        "message": "当前知识库未覆盖该内容",
        "closest": node.id if node else None,
        "closest_name": node.name if node else None,
    }
