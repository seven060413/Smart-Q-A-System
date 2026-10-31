"""实体链接：把问句中的概念映射到图谱知识点节点。

方法（由简到繁）：
1. 字符二元组 Dice 系数：衡量节点名与问句的字符片段共现，对中文无分词不敏感；
2. 字符覆盖度：节点名中有多大比例的字出现在问句中，作为兜底信号；
3. 句向量（bge-m3）：语义相似度，后续可作增强（见 retrieval.BgeM3Embedder）。

加权：score = 0.7 * dice + 0.3 * coverage。

全量图谱下的过滤规则（避免短别名/英文别名造成误匹配）：
- 单字候选（如「比」「时」「图」）不参与模糊打分，只允许通过精确问句模式命中；
- 纯英文候选（如 aliases 中的 plane/slope）必须作为完整单词出现，不能在
  apple/Photoshop 这样的单词内部命中；
- 其余候选仍按 Dice + 覆盖度打分。

精确命中用于低分兜底：问句里出现完整知识点名（单字名要求「什么是 X / X 是什么」
等问法）时，即使模糊分数低于阈值也接受，避免短名的合法问题被拒答。
"""

import re
from typing import List, Optional, Tuple

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


# 单字知识点允许的精确问法：只在这些明确问法下命中，避免「足球比赛」命中「比」。
_SINGLE_CHAR_PATTERNS = (
    "什么是{0}",
    "{0}是什么",
    "{0}表示什么",
    "{0}的含义",
    "{0}的意思",
)


def _ascii_word_in(candidate: str, question: str) -> bool:
    """英文候选必须作为完整单词出现，避免 plane 命中 apple、slope 命中 Photoshop。"""
    pattern = rf"(?<![A-Za-z0-9]){re.escape(candidate)}(?![A-Za-z0-9])"
    return re.search(pattern, question, flags=re.IGNORECASE) is not None


def _candidate_allowed(candidate: str, question: str) -> bool:
    """是否允许该候选参与模糊打分。"""
    if not candidate or len(candidate) < 2:
        return False
    if candidate.isascii():
        return _ascii_word_in(candidate, question)
    return True


def _candidate_exact(candidate: str, question: str) -> bool:
    """问句是否明确提到了完整候选名。"""
    if not candidate:
        return False
    if candidate.isascii():
        return _ascii_word_in(candidate, question)
    if len(candidate) == 1:
        return any(pattern.format(candidate) in question for pattern in _SINGLE_CHAR_PATTERNS)
    return candidate in question


def link_entity(question: str, nodes: List[Node], top_k: int = 3) -> List[Tuple[Node, float]]:
    """把问句链接到最相似的知识点节点（Concept/Skill），返回 [(node, score), ...] 降序。

    候选文本 = 节点名 + 别名（aliases），取最高分的候选作为该节点得分。
    单字候选和英文别名的处理见模块说明。
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
            if not _candidate_allowed(cand, question):
                continue
            dice = _dice(_bigrams(cand), q_bigrams)
            cov = _coverage(set(cand), q_chars)
            best = max(best, 0.7 * dice + 0.3 * cov)
        scored.append((n, best))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def find_exact_match(question: str, nodes: List[Node]) -> Optional[Node]:
    """在问句中寻找明确出现的知识点名/别名。

    优先选择更长的候选，避免「什么是真分数」同时命中「真分数」和「分数」时选短名。
    仅在模糊匹配低于阈值时作为兜底使用。
    """
    best_node: Optional[Node] = None
    best_key = (-1, False)
    for n in nodes:
        if n.label not in ("Concept", "Skill"):
            continue
        candidates = [n.name] + list(n.properties.get("aliases") or [])
        for cand in candidates:
            if not _candidate_exact(cand, question):
                continue
            key = (len(cand), cand == n.name)
            if key > best_key:
                best_key = key
                best_node = n
    return best_node
