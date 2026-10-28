"""把现有 JSON 图谱导入 SQLite（阶段 2）。

设计要点：
- 原始 JSON 只读，绝不删除、不覆盖；数据库只是导入副本。
- 同一 version_id 重复导入时：内容一致（sha256 相同）则跳过；不一致则报错，
  除非显式 ``force=True`` 才先删除该版本旧数据再重导。
- 边目标统一走 graph_edge_targets：标量 target 一行，target_name_to_ids 列表多行，
  避免沿用只导入标量 target 的逻辑漏掉 tests_concept / tests_skill。
- 全部写入包在一个事务里，失败回滚，不留半截数据。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import db as db_module
from .schema import _utcnow

# 边字段中属于「结构」的键；其余字段（如 source_stem）合并进 properties_json，保证不丢。
_EDGE_STRUCT_KEYS = frozenset(
    {"source", "source_name", "target", "target_name", "target_name_to_ids", "type", "properties"}
)


@dataclass
class ImportReport:
    """一次导入的结果，供脚本打印与测试断言。"""

    version_id: str
    source_path: str
    source_sha256: str
    skipped: bool = False
    node_count: int = 0
    edge_count: int = 0
    target_row_count: int = 0
    scalar_edge_count: int = 0
    special_edge_count: int = 0
    missing_target_edges: int = 0
    orphan_source_edges: int = 0
    orphan_target_rows: int = 0
    node_label_counts: dict = field(default_factory=dict)
    edge_type_counts: dict = field(default_factory=dict)


def sha256_file(path: Path) -> str:
    """计算文件内容的 SHA-256（十六进制），用于内容指纹与重复导入判断。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json_graph(path: Path) -> tuple[list[dict], list[dict]]:
    """读取 JSON 图谱，返回 (nodes, edges)。只读取，不修改原文件。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    return nodes, edges


def _edge_targets(e: dict) -> list[tuple[int, str, str | None]]:
    """返回边的目标列表 [(ordinal, target_key, target_name), ...]。

    - 标量边：``target`` → 一行；
    - 特殊边：``target_name_to_ids`` → 多行；
    - 两者都没有 → 空列表（导入时记为遗漏异常）。
    """
    if "target" in e:
        return [(0, e["target"], e.get("target_name"))]
    if "target_name_to_ids" in e:
        return [
            (i, t["target"], t.get("target_name"))
            for i, t in enumerate(e["target_name_to_ids"])
        ]
    return []


def _edge_properties(e: dict) -> dict:
    """把非结构字段合并进 properties，保证 source_stem 等附加字段不丢。"""
    extra = {k: v for k, v in e.items() if k not in _EDGE_STRUCT_KEYS}
    props = dict(e.get("properties") or {})
    props.update(extra)
    return props


def version_id_for(course_id: str, scope: str, book_id: str | None) -> str:
    """确定性生成图谱版本主键，便于幂等导入与溯源。"""
    if scope == "subject_full":
        return f"{course_id}:subject_full"
    if scope == "book":
        assert book_id, "scope=book 必须提供 book_id"
        return f"{course_id}:book:{book_id}"
    return f"{course_id}:custom:{book_id or 'unnamed'}"


def active_slot_for(scope: str, book_id: str | None) -> str:
    """启用槽位：同课程同槽位只允许一个启用版本。"""
    if scope == "book":
        return f"book:{book_id}"
    return scope


def _ensure_course(conn, course_id: str, name: str, subject: str) -> None:
    """幂等插入课程；已存在则不动。"""
    now = _utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO courses (id, code, name, subject, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (course_id, course_id, name, subject, now, now),
    )


def _delete_version_data(conn, version_id: str) -> None:
    """按依赖顺序删除某版本的全部图谱数据（在事务内调用）。"""
    conn.execute("DELETE FROM graph_edge_targets WHERE graph_version_id = ?", (version_id,))
    conn.execute("DELETE FROM graph_edges WHERE graph_version_id = ?", (version_id,))
    conn.execute("DELETE FROM graph_nodes WHERE graph_version_id = ?", (version_id,))
    conn.execute("DELETE FROM graph_versions WHERE id = ?", (version_id,))


def _count_nodes(conn, version_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS c FROM graph_nodes WHERE graph_version_id = ?", (version_id,)
    ).fetchone()["c"]


def version_stats(conn, version_id: str) -> dict:
    """返回某图谱版本的节点/边/目标行计数（不存在时各为 0）。"""
    row = conn.execute(
        "SELECT id, source_path FROM graph_versions WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        return {"exists": False, "version_id": version_id, "nodes": 0, "edges": 0, "targets": 0}
    return {
        "exists": True,
        "version_id": version_id,
        "source_path": row["source_path"],
        "nodes": _count_nodes(conn, version_id),
        "edges": conn.execute(
            "SELECT COUNT(*) AS c FROM graph_edges WHERE graph_version_id = ?", (version_id,)
        ).fetchone()["c"],
        "targets": conn.execute(
            "SELECT COUNT(*) AS c FROM graph_edge_targets WHERE graph_version_id = ?", (version_id,)
        ).fetchone()["c"],
    }


def delete_version(conn, version_id: str) -> dict:
    """删除某个图谱版本及其全部节点/边数据（事务内）。

    返回删除前统计；版本不存在时返回 exists=False。原始 JSON 不受影响。
    """
    before = version_stats(conn, version_id)
    if not before["exists"]:
        return before
    conn.execute("BEGIN")
    try:
        _delete_version_data(conn, version_id)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return before


def import_graph(
    conn,
    json_path,
    *,
    course_id: str = "math",
    course_name: str = "小学数学",
    subject: str = "math",
    scope: str = "subject_full",
    book_id: str | None = None,
    dataset_name: str = "K12-KGraph math",
    dataset_version: str | None = None,
    metadata: dict | None = None,
    force: bool = False,
    make_active: bool = True,
) -> ImportReport:
    """导入一个 JSON 图谱到 SQLite，返回 ImportReport。

    全部写入在一个事务内；任何异常都会回滚。重复导入行为见模块 docstring。
    """
    path = Path(json_path)
    digest = sha256_file(path)
    version_id = version_id_for(course_id, scope, book_id)
    slot = active_slot_for(scope, book_id)
    now = _utcnow()

    nodes, edges = load_json_graph(path)

    # 重复导入判断（导入前先看版本是否已存在）。
    existing = conn.execute(
        "SELECT source_sha256 FROM graph_versions WHERE id = ?", (version_id,)
    ).fetchone()
    if existing is not None:
        if existing["source_sha256"] == digest:
            return ImportReport(
                version_id=version_id,
                source_path=str(path),
                source_sha256=digest,
                skipped=True,
            )
        if not force:
            raise RuntimeError(
                f"图谱版本 {version_id} 已存在但内容不同（源文件 {path} 已变化）；"
                f"请用 --force 显式重新导入，或更换 version id。"
            )

    # 节点 id 去重校验：重复会触发 UNIQUE 约束，这里提前给出更清晰的报错。
    seen: set[str] = set()
    dup_nodes: list[str] = []
    for n in nodes:
        nid = n["id"]
        if nid in seen:
            dup_nodes.append(nid)
        seen.add(nid)
    if dup_nodes:
        raise ValueError(f"源文件节点 id 重复（示例）: {dup_nodes[:5]}")

    node_ids = seen

    # 边目标统计与悬空校验（只报告，不静默丢弃）。
    scalar_edge_count = 0
    special_edge_count = 0
    missing_target_edges = 0
    orphan_source_edges = 0
    orphan_target_rows = 0
    target_row_count = 0
    edge_type_counts: dict[str, int] = {}

    for e in edges:
        etype = e["type"]
        edge_type_counts[etype] = edge_type_counts.get(etype, 0) + 1
        if e["source"] not in node_ids:
            orphan_source_edges += 1
        targets = _edge_targets(e)
        if not targets:
            missing_target_edges += 1
            continue
        if "target" in e:
            scalar_edge_count += 1
        else:
            special_edge_count += 1
        for _, tkey, _ in targets:
            target_row_count += 1
            if tkey not in node_ids:
                orphan_target_rows += 1

    node_label_counts: dict[str, int] = {}
    for n in nodes:
        node_label_counts[n["label"]] = node_label_counts.get(n["label"], 0) + 1

    # 悬空引用会违反外键约束；在写事务前显式报错，比让 SQLite 半途回滚更清晰。
    if orphan_source_edges or orphan_target_rows:
        raise ValueError(
            f"图谱存在悬空引用：源节点缺失 {orphan_source_edges} 条，目标节点缺失 "
            f"{orphan_target_rows} 行。请确认源 JSON 的节点集合是否完整。"
        )

    # —— 事务内写入 ——
    try:
        conn.execute("BEGIN")

        if existing is not None and force:
            _delete_version_data(conn, version_id)

        _ensure_course(conn, course_id, course_name, subject)

        conn.execute(
            "INSERT INTO graph_versions "
            "(id, course_id, scope, book_id, active_slot, dataset_name, dataset_version, "
            " source_path, source_sha256, imported_at, is_active, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                version_id,
                course_id,
                scope,
                book_id,
                slot,
                dataset_name,
                dataset_version,
                str(path),
                digest,
                now,
                1 if make_active else 0,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )

        for n in nodes:
            conn.execute(
                "INSERT INTO graph_nodes (graph_version_id, node_key, label, name, properties_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    version_id,
                    n["id"],
                    n["label"],
                    n["name"],
                    json.dumps(n.get("properties", {}), ensure_ascii=False),
                ),
            )

        for idx, e in enumerate(edges):
            cur = conn.execute(
                "INSERT INTO graph_edges "
                "(graph_version_id, source_key, source_name, type, source_edge_index, properties_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    e["source"],
                    e.get("source_name"),
                    e["type"],
                    idx,
                    json.dumps(_edge_properties(e), ensure_ascii=False),
                ),
            )
            edge_id = cur.lastrowid
            for ordinal, tkey, tname in _edge_targets(e):
                conn.execute(
                    "INSERT INTO graph_edge_targets "
                    "(edge_id, graph_version_id, ordinal, target_key, target_name) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (edge_id, version_id, ordinal, tkey, tname),
                )

        conn.commit()
    except BaseException:
        conn.rollback()
        raise

    # —— 导入后校验计数 ——
    report = ImportReport(
        version_id=version_id,
        source_path=str(path),
        source_sha256=digest,
        node_count=_count_nodes(conn, version_id),
        edge_count=conn.execute(
            "SELECT COUNT(*) AS c FROM graph_edges WHERE graph_version_id = ?", (version_id,)
        ).fetchone()["c"],
        target_row_count=conn.execute(
            "SELECT COUNT(*) AS c FROM graph_edge_targets WHERE graph_version_id = ?", (version_id,)
        ).fetchone()["c"],
        scalar_edge_count=scalar_edge_count,
        special_edge_count=special_edge_count,
        missing_target_edges=missing_target_edges,
        orphan_source_edges=orphan_source_edges,
        orphan_target_rows=orphan_target_rows,
        node_label_counts=node_label_counts,
        edge_type_counts=edge_type_counts,
    )
    return report
