"""问答流水线：实体链接 → 拒答判定 → 前置诊断 + 学习路径 + 溯源 → 组装提示词。

不调用大模型，便于单元测试；answer 字段由上层生成器填充。
"""

from .diagnosis import diagnose, format_citation
from .learning_path import build_learning_path
from .refusal import LINK_THRESHOLD, link_top


def build_prompt(question, node, diag, path, citation, graph) -> str:
    """构建生成提示词：只允许用给定证据回答，面向中小学生，分层输出。"""
    required = [graph.nodes[i]["name"] for i in diag["required"]]
    suggested = [graph.nodes[i]["name"] for i in diag["suggested"]]
    consolidation = [graph.nodes[i]["name"] for i in path["consolidation"]]
    body_desc = node.properties.get("definition", "") or node.properties.get("description", "")

    return f"""你是小学数学助教，面向中小学生讲解。请严格只用下面提供的图谱证据回答，
不得编造教材中没有的内容；若证据不足以回答，必须明确说「当前知识库未覆盖该内容」。

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

请按三层结构分层回答：
1. 先补前置：一句话点出学生需要先会的知识；
2. 再讲本体：用通俗语言分步讲解，可举教材例子；
3. 巩固延伸：给出一个练习方向。
"""


def run_qa(question, graph, kp_nodes) -> dict:
    """运行问答流水线（不含大模型生成），返回结构化结果与生成用提示词。"""
    node, score = link_top(question, kp_nodes)

    # 拒答：链接分数低于阈值 → 知识库未覆盖
    if node is None or score < LINK_THRESHOLD:
        closest = node.name if node else None
        msg = "当前知识库未覆盖该内容"
        if closest:
            msg += f"，最接近：{closest}"
        return {
            "answer": msg,
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

    gaps = [{"name": graph.nodes[i]["name"], "required": True} for i in diag["required"]]
    gaps += [{"name": graph.nodes[i]["name"], "required": False} for i in diag["suggested"]]

    learning_path = {
        "prerequisites": [graph.nodes[i]["name"] for i in path["prerequisites"]],
        "body": node.name,
        "consolidation": [graph.nodes[i]["name"] for i in path["consolidation"]],
    }

    return {
        "answer": None,
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
