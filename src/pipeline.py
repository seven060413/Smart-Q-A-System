"""问答流水线：实体链接 → 拒答判定 → 前置诊断 + 学习路径 + 溯源 → 组装提示词。

不调用大模型，便于单元测试；answer 字段由上层生成器填充。
"""

import re

from .diagnosis import diagnose, format_citation
from .learning_path import build_learning_path
from .refusal import link_top
from .settings import qa_link_threshold

# 生成结果里「巩固练习」段的标题。兼容模型偶尔写成 Markdown 标题。
_EXERCISE_HEADING_RE = re.compile(
    r"(?:【\s*巩固练习\s*】|##+\s*巩固练习\s*"
    r"|^\s*(?:\d+\s*[.、．)）]\s*)?巩固练习\s*[:：]?\s*$)",
    re.M,
)
# 练习题编号：1. / 1、/ 1) / （1） / 一、 / - / * / •
_EXERCISE_ITEM_RE = re.compile(
    r"^\s*(?:\d+\s*[.、．)）]|[（(]\s*\d+\s*[）)]"
    r"|[一二三四五六七八九十]+\s*[、.．]|[-*•])\s*"
)


def _parse_exercises(block: str) -> list[str]:
    """把「巩固练习」段落拆成题目列表。

    优先按编号拆；没有编号时按空行分组，最后整体作为一道题。
    题目里的「答案：」行会保留在该题内，前端按 pre-wrap 展示。
    """
    block = (block or "").strip()
    if not block:
        return []

    lines = [line.strip() for line in block.splitlines() if line.strip()]
    items: list[str] = []
    current: list[str] = []
    numbered = False
    for line in lines:
        if _EXERCISE_ITEM_RE.match(line):
            numbered = True
            if current:
                items.append("\n".join(current).strip())
            current = [_EXERCISE_ITEM_RE.sub("", line, count=1).strip()]
        else:
            current.append(line)
    if current:
        items.append("\n".join(current).strip())

    if not numbered:
        groups = [g.strip() for g in re.split(r"\n\s*\n", block) if g.strip()]
        return groups or ["\n".join(lines)]
    return [item for item in items if item]


def split_generated_answer(text: str) -> tuple[str, list[str]]:
    """把生成结果拆成「讲解正文」和「巩固练习题」。

    兼容旧格式：没有【巩固练习】标题时，整段都作为正文，题目列表为空。
    """
    raw = (text or "").strip()
    if not raw:
        return "", []

    match = _EXERCISE_HEADING_RE.search(raw)
    if match is None:
        return raw, []

    answer = raw[: match.start()].strip()
    # 去掉模型可能保留的「【讲解】/## 讲解」标题，前端已经有自己的折叠标题。
    answer = re.sub(r"^\s*(?:【\s*讲解\s*】|##+\s*讲解)\s*", "", answer).strip()
    exercises = _parse_exercises(raw[match.end() :])
    if not answer:
        # 模型只给了练习、没有讲解时，不要把整段原文丢掉。
        answer = raw.strip()
    return answer, exercises


def build_prompt(question, node, diag, path, citation, graph) -> str:
    """构建生成提示词：只允许用给定证据回答，面向中小学生，分层输出。"""
    required = [graph.nodes[i]["name"] for i in diag["required"]]
    suggested = [graph.nodes[i]["name"] for i in diag["suggested"]]
    consolidation = [graph.nodes[i]["name"] for i in path["consolidation"]]
    body_desc = node.properties.get("definition", "") or node.properties.get("description", "")

    return f"""你是中小学数学助教，面向中小学生讲解。请严格只用下面提供的图谱证据回答，
不得编造知识图谱中没有的内容；若证据不足以回答，必须明确说「当前知识库未覆盖该内容」。

【学生问题】
{question}

【本体知识点】
{node.name}：{body_desc}

【前置知识（必需）】
{"、".join(required) if required else "无"}

【建议补充的前置】
{"、".join(suggested) if suggested else "无"}

【巩固延伸】
{"、".join(consolidation) if consolidation else "无"}

【教材出处】
{citation}

请严格按下面两段格式输出，不要输出其他标题或额外说明：

【讲解】
1. 先补前置：一句话点出学生需要先会的知识。
2. 再讲本体：用通俗语言分步讲解，可举教材例子。

【巩固练习】
1. 题目：围绕本体知识点出 1 道基础题；下一行写「答案：」并给出简短答案或提示。
2. 题目：再出 1 道稍难的题；下一行写「答案：」并给出简短答案或提示。

练习必须围绕「{node.name}」及上面提供的图谱证据，不引入新的知识点。
"""


def run_qa(question, graph, kp_nodes, threshold: float | None = None) -> dict:
    """运行问答流水线（不含大模型生成），返回结构化结果与生成用提示词。

    threshold 为空时读取 QA_LINK_THRESHOLD（默认 0.35）；测试可显式传入。
    """
    if threshold is None:
        threshold = qa_link_threshold()
    node, score = link_top(question, kp_nodes, threshold)

    # 拒答：链接分数低于阈值 → 知识库未覆盖
    if node is None or score < threshold:
        closest = node.name if node else None
        msg = "当前知识库未覆盖该内容"
        if closest:
            msg += f"，最接近：{closest}"
        return {
            "answer": msg,
            "exercises": [],
            "knowledge_point": closest,
            "prerequisite_gaps": [],
            "learning_path": None,
            "source": None,
            "refused": True,
            "prompt": None,
        }

    diag = diagnose(graph, node.id)
    path = build_learning_path(graph, node.id)
    citation = format_citation(graph, node.id)

    # 名称用于展示，id 是稳定节点键，供视频检索等下游功能使用。
    gaps = [
        {"id": i, "name": graph.nodes[i]["name"], "required": True}
        for i in diag["required"]
    ]
    gaps += [
        {"id": i, "name": graph.nodes[i]["name"], "required": False}
        for i in diag["suggested"]
    ]

    learning_path = {
        "prerequisites": [graph.nodes[i]["name"] for i in path["prerequisites"]],
        "prerequisite_ids": list(path["prerequisites"]),
        "body": node.name,
        "body_id": node.id,
        "consolidation": [graph.nodes[i]["name"] for i in path["consolidation"]],
        "consolidation_ids": list(path["consolidation"]),
        # 由 _fill_answer 生成后填入；先占位，保证接口字段稳定。
        "exercises": [],
    }

    return {
        "answer": None,
        "exercises": [],
        "knowledge_point": node.name,
        "prerequisite_gaps": gaps,
        "learning_path": learning_path,
        "source": citation,
        "refused": False,
        "prompt": build_prompt(question, node, diag, path, citation, graph),
        # 内部结构化元数据：供聊天持久化保存知识点 id；API 返回前会移除。
        "_meta": {
            "body": {"id": node.id, "name": node.name},
            "required": [
                {"id": i, "name": graph.nodes[i]["name"]} for i in diag["required"]
            ],
            "suggested": [
                {"id": i, "name": graph.nodes[i]["name"]} for i in diag["suggested"]
            ],
            "prerequisites": [
                {"id": i, "name": graph.nodes[i]["name"]}
                for i in path["prerequisites"]
            ],
            "consolidation": [
                {"id": i, "name": graph.nodes[i]["name"]}
                for i in path["consolidation"]
            ],
        },
    }
