"""生成结果拆分与提示词年级上下文的单元测试。"""

from src.graph import build_digraph
from src.models import Edge, Node
from src.pipeline import run_qa, split_generated_answer


def _qa_prompt(student_grade=None):
    graph = build_digraph(
        [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")],
        [Edge("B", "A", "prerequisites_for")],
    )
    nodes = [Node("A", "Concept", "甲"), Node("B", "Concept", "乙")]
    result = run_qa("什么是甲", graph, nodes, student_grade=student_grade)
    return result["prompt"]


def test_提示词包含年级背景():
    prompt = _qa_prompt(3)
    assert "【学生背景】" in prompt
    assert "三年级" in prompt
    assert "不是内容限制" in prompt
    # 跨年级问题仍要完整回答。
    assert "仍然完整回答" in prompt


def test_未设置年级时提示词不含年级背景():
    prompt = _qa_prompt()
    assert "【学生背景】" not in prompt


def test_拆分讲解与巩固练习():
    text = """【讲解】
1. 先补前置：先会分数单位。
2. 再讲本体：分子比分母小的分数是真分数。

【巩固练习】
1. 题目：判断 3/5、7/3 哪些是真分数。
答案：3/5，因为分子小于分母。
2. 题目：写出一个分母为 8 的真分数。
答案：1/8（答案不唯一）。
"""
    answer, exercises = split_generated_answer(text)
    assert "巩固练习" not in answer
    assert "先补前置" in answer and "再讲本体" in answer
    assert len(exercises) == 2
    assert exercises[0].startswith("题目：判断")
    assert "答案：3/5" in exercises[0]
    assert exercises[1].startswith("题目：写出")


def test_没有巩固练习标题时整段作为正文():
    answer, exercises = split_generated_answer("这是一段普通讲解。")
    assert answer == "这是一段普通讲解。"
    assert exercises == []


def test_兼容Markdown标题与破折号编号():
    text = """## 讲解
讲解正文。

## 巩固练习
- 题目：求 1/2 + 1/3。
答案：5/6。
- 题目：求 2/3 - 1/4。
答案：5/12。
"""
    answer, exercises = split_generated_answer(text)
    assert answer == "讲解正文。"
    assert len(exercises) == 2
    assert "1/2 + 1/3" in exercises[0]
