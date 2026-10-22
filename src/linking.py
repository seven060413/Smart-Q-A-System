"""实体链接：把问句中的概念映射到图谱知识点节点。

方法（由简到繁）：
1. 字符二元组 Dice 系数：衡量节点名与问句的字符片段共现，对中文无分词不敏感；
2. 字符覆盖度：节点名中有多大比例的字出现在问句中，作为兜底信号；
3. 句向量（bge-m3）：语义相似度，后续可作增强（见 retrieval.BgeM3Embedder）。

加权：score = 0.7 * dice + 0.3 * coverage。
依据：Dice 关注「共现片段」，能区分「异分母分数加减法」与「通分」这类包含/局部关系
（后者虽字全命中，但只有 2 个字、片段太短，Dice 很低）；覆盖度兜底处理片段不连续但
字面相关的场景。两个信号都归一化到 [0,1] 后才加权，量纲一致。
"""

from typing import List, Tuple

from .models import Node


def _bigrams(s: str) -> set:
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _dice(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return 2 * len(a & b) / (len(a) + len(b))


def _coverage(node_chars: set, question_chars: set) -> float:
    if not node_chars:
        return 0.0
    return len(node_chars & question_chars) / len(node_chars)


def link_entity(question: str, nodes: List[Node], top_k: int = 3) -> List[Tuple[Node, float]]:
    """把问句链接到最相似的知识点节点（Concept/Skill），返回 [(node, score), ...] 降序。

    候选文本 = 节点名 + 别名（aliases），取最高分的候选作为该节点得分。
    """
    q_chars = set(question)
    q_bigrams = _bigrams(question)
    scored: List[Tuple[Node, float]] = []
    for n in nodes:
        if n.label not in ("Concept", "Skill"):
            continue
        best = 0.0
        candidates = [n.name] + list(n.properties.get("aliases") or [])
        for cand in candidates:
            dice = _dice(_bigrams(cand), q_bigrams)
            cov = _coverage(set(cand), q_chars)
            best = max(best, 0.7 * dice + 0.3 * cov)
        scored.append((n, best))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]
