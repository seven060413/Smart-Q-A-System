"""阶段 2：图谱导入测试（覆盖标量边、特殊边、幂等、force、异常）。"""

import json

import pytest

from src import db as db_module
from src.graph_import import delete_version, import_graph, version_stats
from src.schema import apply_migrations


@pytest.fixture
def conn():
    c = db_module.connect(":memory:")
    apply_migrations(c)
    yield c
    c.close()


def _write(tmp_path, nodes, edges):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False), encoding="utf-8")
    return p


def _sample_nodes():
    return [
        {"id": "cpt1", "label": "Concept", "name": "异分母分数加减法", "properties": {"definition": "..."}},
        {"id": "cpt2", "label": "Concept", "name": "通分方法", "properties": {}},
        {"id": "exe1", "label": "Exercise", "name": "习题1", "properties": {"stem": "题干"}},
    ]


def test_import_scalar_and_special_edges(conn, tmp_path):
    nodes = _sample_nodes()
    edges = [
        # 标量边
        {"source": "cpt1", "source_name": "异分母", "target": "cpt2", "target_name": "通分方法",
         "type": "prerequisites_for", "properties": {"relations": "..."}},
        # 特殊边：target_name_to_ids 列表，两个目标
        {"source": "exe1", "source_stem": "看图比较", "type": "tests_concept",
         "target_name_to_ids": [
             {"target": "cpt1", "target_name": "异分母分数加减法"},
             {"target": "cpt2", "target_name": "通分方法"},
         ]},
    ]
    p = _write(tmp_path, nodes, edges)

    r = import_graph(conn, p, scope="subject_full")

    assert not r.skipped
    assert r.node_count == 3
    assert r.edge_count == 2
    assert r.scalar_edge_count == 1
    assert r.special_edge_count == 1
    assert r.target_row_count == 3          # 1 标量 + 2 特殊
    assert r.missing_target_edges == 0
    assert r.orphan_source_edges == 0
    assert r.orphan_target_rows == 0

    # 特殊边的两个目标都进了 graph_edge_targets
    n_targets = conn.execute(
        "SELECT COUNT(*) AS c FROM graph_edge_targets t "
        "JOIN graph_edges e ON e.id = t.edge_id "
        "WHERE e.type = 'tests_concept'"
    ).fetchone()["c"]
    assert n_targets == 2

    # 特殊边 source_stem 被合并进 properties_json，未丢失
    row = conn.execute(
        "SELECT properties_json FROM graph_edges WHERE type = 'tests_concept'"
    ).fetchone()
    assert "source_stem" in json.loads(row["properties_json"])


def test_import_idempotent_skip(conn, tmp_path):
    p = _write(tmp_path, _sample_nodes(),
               [{"source": "cpt1", "target": "cpt2", "type": "prerequisites_for"}])
    first = import_graph(conn, p, scope="subject_full")
    second = import_graph(conn, p, scope="subject_full")

    assert not first.skipped
    assert second.skipped
    assert conn.execute("SELECT COUNT(*) AS c FROM graph_versions").fetchone()["c"] == 1


def test_import_force_reimport(conn, tmp_path):
    p = _write(tmp_path, _sample_nodes(),
               [{"source": "cpt1", "target": "cpt2", "type": "prerequisites_for"}])
    import_graph(conn, p, scope="subject_full")

    # 改变源文件内容（sha256 变化），force=True 重新导入
    p.write_text(json.dumps({"nodes": _sample_nodes(), "edges": []}, ensure_ascii=False), encoding="utf-8")
    r = import_graph(conn, p, scope="subject_full", force=True)

    assert not r.skipped
    assert r.edge_count == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM graph_edges").fetchone()["c"] == 0


def test_import_changed_source_requires_force(conn, tmp_path):
    p = _write(tmp_path, _sample_nodes(),
               [{"source": "cpt1", "target": "cpt2", "type": "prerequisites_for"}])
    import_graph(conn, p, scope="subject_full")
    p.write_text(json.dumps({"nodes": _sample_nodes(), "edges": []}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError, match="--force"):
        import_graph(conn, p, scope="subject_full")


def test_import_missing_target_edge_reported(conn, tmp_path):
    nodes = _sample_nodes()
    edges = [{"source": "cpt1", "type": "prerequisites_for"}]  # 无 target 也无列表
    p = _write(tmp_path, nodes, edges)
    r = import_graph(conn, p, scope="subject_full")

    assert r.missing_target_edges == 1
    assert r.target_row_count == 0
    # 边本身仍被保留（可溯源），只是没有目标行
    assert conn.execute("SELECT COUNT(*) AS c FROM graph_edges").fetchone()["c"] == 1


def test_import_orphan_source_raises(conn, tmp_path):
    nodes = _sample_nodes()
    edges = [{"source": "missing", "target": "cpt1", "type": "relates_to"}]
    p = _write(tmp_path, nodes, edges)
    with pytest.raises(ValueError, match="悬空引用"):
        import_graph(conn, p, scope="subject_full")


def test_import_duplicate_node_id_raises(conn, tmp_path):
    nodes = _sample_nodes() + [{"id": "cpt1", "label": "Concept", "name": "重复", "properties": {}}]
    edges = [{"source": "cpt1", "target": "cpt2", "type": "relates_to"}]
    p = _write(tmp_path, nodes, edges)
    with pytest.raises(ValueError, match="重复"):
        import_graph(conn, p, scope="subject_full")


def test_import_book_version_requires_book_id(conn, tmp_path):
    p = _write(tmp_path, _sample_nodes(),
               [{"source": "cpt1", "target": "cpt2", "type": "relates_to"}])
    r = import_graph(conn, p, scope="book", book_id="math_5b_rjb")
    assert r.version_id == "math:book:math_5b_rjb"


def test_delete_version_removes_all_data(conn, tmp_path):
    p = _write(tmp_path, _sample_nodes(),
               [{"source": "cpt1", "target": "cpt2", "type": "relates_to"}])
    import_graph(conn, p, scope="subject_full")

    before = version_stats(conn, "math:subject_full")
    assert before["nodes"] == 3

    deleted = delete_version(conn, "math:subject_full")
    assert deleted["exists"] is True
    assert deleted["nodes"] == 3

    after = version_stats(conn, "math:subject_full")
    assert after["exists"] is False
    assert after["nodes"] == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM graph_edges").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) AS c FROM graph_edge_targets").fetchone()["c"] == 0


def test_delete_version_missing_is_noop(conn):
    result = delete_version(conn, "math:nonexistent")
    assert result["exists"] is False
