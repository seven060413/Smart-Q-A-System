"""拒答：知识库未覆盖的问题明确拒答，并给出最接近的已覆盖知识点。

依据（溯源/拒答 功能 6）：
- 实体链接分数低于阈值 → 判定「知识库未覆盖」，拒绝回答、绝不猜测；
- 返回链接分数最高的知识点作为「最接近」提示；
- 问句明确包含知识点名/别名时，用精确命中兜底，避免短名合法问题被拒答。
"""

from typing import Dict, Tuple

from .linking import find_exact_match, link_entity

# 链接分数阈值：低于该值视为知识库未覆盖。
#
# 全量图谱（1898 个 Concept/Skill）下的标定结果（见 docs/qa/问答覆盖范围扩展与评估.md）：
# - 50 条数学域外问题在过滤短别名/英文别名后最高 0.288；
# - 12 条自然数学问题最低 0.46；
# - 1898 条「什么是{知识点名}」中，除 24 个单字名外均 >= 0.7；
#   单字名由精确问法兜底（什么是 X / X 是什么）。
# 因此取 0.35：高于域外样本，低于自然问题样本。
LINK_THRESHOLD = 0.35


def link_top(
    question: str, nodes, threshold: float = LINK_THRESHOLD
) -> Tuple:
    """返回链接最高的 (node, score)；无候选返回 (None, 0.0)。

    模糊分数达到阈值时直接返回；否则尝试完整名称/别名的精确命中。
    精确命中时用 threshold 作为返回分数，表示「已覆盖」，避免短名被拒答。
    """
    hits = link_entity(question, nodes, top_k=1)
    node, score = (hits[0] if hits else (None, 0.0))

    if node is not None and score >= threshold:
        return node, score

    exact = find_exact_match(question, nodes)
    if exact is not None:
        return exact, max(score, threshold)

    return node, score


def is_covered(question: str, nodes, threshold: float = LINK_THRESHOLD) -> bool:
    """判断问题是否被知识库覆盖（链接分数达到阈值）。"""
    _, score = link_top(question, nodes, threshold)
    return score >= threshold


def refusal_message(
    question: str, nodes, threshold: float = LINK_THRESHOLD
) -> Dict:
    """库外问题返回拒答信息（含最接近知识点）。"""
    node, _ = link_top(question, nodes, threshold)
    return {
        "covered": False,
        "message": "当前知识库未覆盖该内容",
        "closest": node.id if node else None,
        "closest_name": node.name if node else None,
    }
