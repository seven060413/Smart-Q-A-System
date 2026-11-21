"""pansgo 数学 K12 过滤、格式转换与目录构建。"""

import json

from src import pansgo


def _fixture():
    topics = [
        {"id": "m1", "name": "小数乘整数", "subject": None, "grade": 3,
         "semester": "上", "chapter": "三年级上册 第1单元", "domain": "数与代数",
         "type": "procedural", "description": "d1", "mastery_criteria": ["c1"],
         "diagnostic_question": {"question": "q", "answer": "a"},
         "external": False, "standards": [{"id": "s1"}]},
        {"id": "m2", "name": "小数乘法", "subject": "math", "grade": 4,
         "external": False},
        {"id": "m3", "name": "高中内容", "subject": None, "grade": 10,
         "external": False},
        {"id": "c1", "name": "语文", "subject": "chinese", "grade": 3,
         "external": False},
        {"id": "e1", "name": "外部节点", "subject": None, "grade": 3,
         "external": True},
    ]
    deps = [
        {"topicId": "m2", "prerequisiteId": "m1", "strength": "hard", "reason": "r1"},
        {"topicId": "m3", "prerequisiteId": "m1", "strength": "soft"},
        {"topicId": "m1", "prerequisiteId": "c1", "strength": "hard"},
    ]
    questions = [
        {"id": "m1_q1", "topicId": "m1", "difficulty": "basic", "type": "numeric",
         "prompt": "p1", "answer": "3", "explanation": "e", "verify": "3"},
        {"id": "m2_q1", "topicId": "m2", "difficulty": "basic", "type": "choice",
         "prompt": "p2", "answer": "A",
         "choices": [{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
         "figure": "<svg/>"},
        {"id": "m3_q1", "topicId": "m3", "difficulty": "basic", "type": "numeric",
         "prompt": "p3", "answer": "1"},
        {"id": "c1_q1", "topicId": "c1", "difficulty": "basic", "type": "numeric",
         "prompt": "p4", "answer": "1"},
    ]
    return topics, deps, questions


def test_filter_keeps_only_math_grades_1_to_9():
    topics, deps, questions = _fixture()
    filtered = pansgo.filter_math(topics, deps, questions, max_grade=9)

    assert [t["id"] for t in filtered["topics"]] == ["m1", "m2"]
    # 跨边界边（m1->m3）与指向语文的边都被丢掉
    assert filtered["dependencies"] == [
        {"topicId": "m2", "prerequisiteId": "m1", "strength": "hard", "reason": "r1"}
    ]
    assert [q["id"] for q in filtered["questions"]] == ["m1_q1", "m2_q1"]


def test_validate_reports_dangling_and_self_loop():
    topics, deps, questions = _fixture()
    filtered = pansgo.filter_math(topics, deps, questions, max_grade=9)
    assert pansgo.validate(filtered) == []

    broken = {
        "topics": filtered["topics"],
        "dependencies": [{"topicId": "m2", "prerequisiteId": "missing"}],
        "questions": [{"id": "x", "topicId": "unknown", "prompt": "p", "answer": "1"}],
    }
    errors = pansgo.validate(broken)
    assert any("端点不在范围内" in e for e in errors)
    assert any("未知知识点" in e for e in errors)

    self_loop = {
        "topics": filtered["topics"],
        "dependencies": [{"topicId": "m1", "prerequisiteId": "m1"}],
        "questions": [],
    }
    assert any("自环" in e for e in pansgo.validate(self_loop))


def test_build_graph_maps_fields_and_edge_direction():
    topics, deps, questions = _fixture()
    filtered = pansgo.filter_math(topics, deps, questions, max_grade=9)

    payload = pansgo.build_graph(filtered["topics"], filtered["dependencies"], max_grade=9)

    assert payload["node_count"] == 2
    node = next(n for n in payload["nodes"] if n["id"] == "m1")
    assert node["label"] == "Concept"
    assert node["name"] == "小数乘整数"
    assert node["properties"]["grade"] == 3
    assert node["properties"]["diagnostic_question"]["answer"] == "a"
    assert node["properties"]["source"] == pansgo.PRODUCER

    edge = payload["edges"][0]
    # source 是先学（prerequisiteId），target 是后学（topicId）
    assert (edge["source"], edge["target"]) == ("m1", "m2")
    assert edge["type"] == "prerequisites_for"
    assert edge["source_name"] == "小数乘整数"
    assert edge["properties"]["strength"] == "hard"


def test_build_question_bank_cleans_and_sorts():
    topics, deps, questions = _fixture()
    filtered = pansgo.filter_math(topics, deps, questions, max_grade=9)

    payload = pansgo.build_question_bank(filtered["questions"])

    assert payload["count"] == 2
    assert [q["id"] for q in payload["questions"]] == ["m1_q1", "m2_q1"]
    q2 = payload["questions"][1]
    assert q2["choices"][0]["text"] == "对"
    assert q2["figure"] == "<svg/>"
    assert "verify" not in q2


def test_write_json_is_deterministic(tmp_path):
    payload = {"b": 1, "a": [1, 2]}
    p1 = tmp_path / "one.json"
    p2 = tmp_path / "two.json"

    sha1 = pansgo.write_json(p1, payload)
    sha2 = pansgo.write_json(p2, payload)

    assert sha1 == sha2
    assert pansgo.load_json(p1) == payload
    assert json.loads(p1.read_text(encoding="utf-8")) == payload


def test_build_catalog_groups_grade_book_and_chapter():
    topics, deps, questions = _fixture()
    filtered = pansgo.filter_math(topics, deps, questions, max_grade=14)
    catalog = pansgo.build_catalog(filtered["topics"], filtered["questions"])

    assert catalog["topic_count"] == 3
    grades = {g["grade"]: g for g in catalog["grades"]}
    assert grades[3]["label"] == "三年级"
    assert grades[10]["label"] == "高一"

    grade3 = grades[3]
    assert grade3["books"][0]["book"] == "三年级上册"
    chapter = grade3["books"][0]["chapters"][0]
    assert chapter["label"] == "第1单元"
    assert chapter["node_ids"] == ["m1"]
    assert chapter["question_count"] == 1

    # 高中同样进入目录
    assert grades[10]["stage"] == "高中"
    assert any(t["id"] == "m3" for t in catalog["topics"])
