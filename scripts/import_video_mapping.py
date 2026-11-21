"""把人工审核后的视频映射 CSV 导入本地 SQLite。

用法（项目根目录）：
    # 先看统计，不写库（默认）
    .venv/Scripts/python.exe scripts/import_video_mapping.py \
        --csv .tmp-verify/video_mapping_7to9.csv --threshold 0.55

    # 确认后写库（会自动备份）
    .venv/Scripts/python.exe scripts/import_video_mapping.py \
        --csv .tmp-verify/video_mapping_7to9.csv --threshold 0.55 --apply

CSV 约定：
- 建议1~3：自动匹配结果，建议1 作为默认知识点；
- 最终知识点id(多个用;分隔)：人工确认结果，优先级最高；
- 决定：通过 / 拒绝 / 待定；为空时按 threshold 自动决定。

规则：
- 决定=拒绝 → 跳过；
- 决定=通过 → 审核通过（即使分数低于 threshold）；
- 决定为空/待定 → 建议1 得分 >= threshold 才通过；
- 目标是 Section 时，自动展开为该小节下全部 Concept/Skill。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.video_import import (  # noqa: E402
    DEFAULT_COURSE_ID,
    upsert_mapping,
    upsert_video,
)

DEFAULT_CSV = ROOT / ".tmp-verify" / "video_mapping_7to9.csv"
DEFAULT_META_DIR = ROOT / ".tmp-verify" / "bili_metadata"
RAW_GRAPH = ROOT / "data" / "raw" / "math.json"


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def load_graph_index(path: Path):
    """返回 (node_label, section_children, node_name)。

    section_children: Section id -> 该小节下的 Concept/Skill id 集合。
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    label = {n["id"]: n.get("label") for n in data["nodes"]}
    name = {n["id"]: n.get("name", "") for n in data["nodes"]}
    section_children: dict[str, set[str]] = {}
    for e in data.get("edges", []):
        if e.get("type") != "appears_in" or "target" not in e:
            continue
        src, dst = e["source"], e["target"]
        if label.get(src) not in ("Concept", "Skill"):
            continue
        if label.get(dst) == "Section":
            section_children.setdefault(dst, set()).add(src)
    return label, section_children, name


def load_metadata(meta_dir: Path):
    """bvid -> view 接口的 data 对象。"""
    out = {}
    if not meta_dir.exists():
        return out
    for path in meta_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            data = payload.get("data") or {}
            bvid = data.get("bvid") or path.stem
            out[bvid] = data
        except Exception:
            continue
    return out


def split_ids(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    for sep in ("；", "，", ",", "|"):
        value = value.replace(sep, ";")
    return [x.strip() for x in value.split(";") if x.strip()]


def iso_from_ts(ts) -> str | None:
    try:
        if not ts:
            return None
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _score(row, idx: int) -> float:
    raw = (row.get(f"建议{idx}得分") or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def default_targets(row, label):
    """未人工填写时：建议1 + 与建议1同分的建议2/3（只收 Concept/Skill）。

    “正数与负数”同时命中“正数”“负数”时，两条都会保留；
    “有理数比较大小”同时命中两个具体节点时，也都会保留。
    """
    top = _score(row, 1)
    picked = []
    for idx in (1, 2, 3):
        nid = (row.get(f"建议{idx}_id") or "").strip()
        if not nid:
            continue
        lab = label.get(nid)
        sc = _score(row, idx)
        if idx == 1:
            # 建议1 允许是具体知识点或小节（小节会在 resolve_targets 展开）
            if lab in ("Concept", "Skill", "Section"):
                picked.append(nid)
        elif lab in ("Concept", "Skill") and top >= 0.70 and sc >= top - 0.005:
            # 同分候选一并保留（如“正数与负数”同时命中正数/负数）
            picked.append(nid)
    return picked


def resolve_targets(row, label, section_children):
    """返回 (target_node_ids, section_expanded, invalid_ids)。"""
    explicit = split_ids(row.get("最终知识点id(多个用;分隔)") or "")
    source = explicit if explicit else default_targets(row, label)
    targets: list[str] = []
    sections: list[str] = []
    invalid: list[str] = []
    for item in source:
        if label.get(item) in ("Concept", "Skill"):
            targets.append(item)
        elif label.get(item) == "Section":
            sections.append(item)
            targets.extend(sorted(section_children.get(item, set())))
        else:
            invalid.append(item)
    # 去重保序
    seen = set(); unique = []
    for x in targets:
        if x not in seen:
            seen.add(x); unique.append(x)
    return unique, sections, invalid


def rank_for(score: float, target_name: str) -> int:
    """相关度越低、目标越泛化，rank 越大（接口按 rank 升序取前 N 条）。

    rank 0：完全同名；rank 1：高置信具体知识点；rank 2：中等置信；
    rank 3：低置信；目标名 <=2 字再降一档，避免“圆/角/方程”这类泛化视频抢占。
    """
    if score >= 0.999:
        rank = 0
    elif score >= 0.85:
        rank = 1
    elif score >= 0.70:
        rank = 2
    else:
        rank = 3
    if len(target_name.strip()) <= 2:
        rank += 1
    return rank


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="导入审核后的知识点-视频映射")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--db", default=None)
    parser.add_argument("--meta-dir", default=str(DEFAULT_META_DIR))
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--reviewer", default="auto-import-0.55")
    parser.add_argument("--course-id", default=DEFAULT_COURSE_ID)
    parser.add_argument("--apply", action="store_true", help="真正写库；默认只 dry-run")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 行（调试用）")
    parser.add_argument("--report", default=str(ROOT / ".tmp-verify" / "import_report.txt"))
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise SystemExit(f"CSV 不存在: {csv_path}")
    label, section_children, node_name = load_graph_index(RAW_GRAPH)
    metadata = load_metadata(Path(args.meta_dir))

    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    approved_rows = []
    skipped = {"低于阈值": 0, "决定拒绝": 0, "决定待定": 0, "无目标": 0}
    invalid_all = []
    section_rows = 0
    for row in rows:
        decision = (row.get("决定") or "").strip()
        if decision == "拒绝":
            skipped["决定拒绝"] += 1
            continue
        if decision == "待定":
            skipped["决定待定"] += 1
            continue
        score = 0.0
        raw_score = (row.get("建议1得分") or "").strip()
        if raw_score:
            try: score = float(raw_score)
            except ValueError: score = 0.0
        if decision != "通过" and score < args.threshold:
            skipped["低于阈值"] += 1
            continue
        targets, sections, invalid = resolve_targets(row, label, section_children)
        invalid_all.extend(invalid)
        if sections:
            section_rows += 1
        if not targets:
            skipped["无目标"] += 1
            continue
        approved_rows.append((row, score, targets, sections))

    # 统计
    video_keys = set()
    mapping_count = 0
    rank1 = rank2 = 0
    for row, score, targets, _ in approved_rows:
        video_keys.add((row["BV号"], row["分P"]))
        mapping_count += len(targets)
        for _t in targets:
            if score >= 0.70: rank1 += 1
            else: rank2 += 1

    report = []
    report.append(f"CSV: {csv_path}")
    report.append(f"数据库: {db_module.resolve_db_path(args.db)}")
    report.append(f"阈值: {args.threshold}  模式: {'APPLY' if args.apply else 'DRY-RUN'}")
    report.append(f"总行数: {len(rows)}")
    report.append(f"通过行数: {len(approved_rows)}")
    report.append(f"跳过: {skipped}")
    report.append(f"涉及视频(BV+分P): {len(video_keys)}")
    report.append(f"预计映射条数: {mapping_count} (rank1={rank1}, rank2={rank2})")
    report.append(f"包含小节展开的行: {section_rows}")
    if invalid_all:
        report.append(f"非法目标 id: {len(invalid_all)} 示例: {invalid_all[:10]}")
    report.append("")
    report.append("前 10 条将通过的行:")
    for row, score, targets, sections in approved_rows[:10]:
        report.append(
            f"  {row['年级']} P{row['分P']} {row['标题']} "
            f"score={score:.2f} -> {targets[:3]}"
            + (f" sections={sections}" if sections else "")
        )

    report_path = Path(args.report)
    report_path.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\n报告已写入: {report_path}")

    if not args.apply:
        print("\nDRY-RUN：未写库。确认无误后加 --apply。")
        return

    if not approved_rows:
        print("\n没有可导入的行。")
        return

    # 写库（自动备份）
    conn = db_module.connect(args.db)
    try:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = ROOT / "data" / "app" / "backups" / f"ikgr-video-import-{stamp}.db"
        db_module.backup(conn, backup_path)
        print(f"\n已备份数据库: {backup_path}")

        inserted_videos = 0
        inserted_mappings = 0
        with conn:
            for row, score, targets, sections in approved_rows:
                bvid = row["BV号"].strip()
                page = int(row["分P"])
                meta = metadata.get(bvid, {})
                owner = meta.get("owner") or {}
                video_id = upsert_video(
                    conn,
                    bvid=bvid,
                    page=page,
                    title=row["标题"],
                    author=owner.get("name"),
                    duration_seconds=int(row["时长秒"]) if row["时长秒"] else None,
                    cover_url=meta.get("pic"),
                    aid=meta.get("aid"),
                    cid=int(row["cid"]) if row.get("cid") else None,
                    published_at=iso_from_ts(meta.get("pubdate")),
                    metadata={
                        "source": "bilibili-collection",
                        "grade": row["年级"],
                        "chapter": row["章节"],
                        "auto_score": score,
                        "section_ids": sections,
                    },
                    course_id=args.course_id,
                )
                inserted_videos += 1
                for node_key in targets:
                    upsert_mapping(
                        conn,
                        node_key=node_key,
                        video_id=video_id,
                        status="approved",
                        rank=rank_for(score, node_name.get(node_key, "")),
                        reviewer=args.reviewer,
                        note=f"auto-import score={score:.2f} p{page}",
                        relation="explains",
                        course_id=args.course_id,
                    )
                    inserted_mappings += 1

        print(f"写入完成：videos={inserted_videos}, mappings={inserted_mappings}")
        # 简单验证
        n_videos = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        n_map = conn.execute("SELECT COUNT(*) FROM knowledge_point_videos").fetchone()[0]
        n_ok = conn.execute(
            "SELECT COUNT(*) FROM knowledge_point_videos WHERE review_status='approved'"
        ).fetchone()[0]
        print(f"库内总计：videos={n_videos}, mappings={n_map}, approved={n_ok}")
        sample = conn.execute(
            "SELECT node_key, COUNT(*) c FROM knowledge_point_videos "
            "WHERE review_status='approved' AND node_key LIKE 'math_7%' "
            "GROUP BY node_key ORDER BY c DESC LIMIT 5"
        ).fetchall()
        print("样例节点映射数：", [dict(r) for r in sample])
    finally:
        conn.close()


if __name__ == "__main__":
    main()
