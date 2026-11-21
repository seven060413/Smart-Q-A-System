"""下载并过滤 cn-math-taxonomy 数学 K12（1–14 年级）数据。

用法（项目根目录执行）：
    .venv/Scripts/python.exe scripts/fetch_pansgo.py
    .venv/Scripts/python.exe scripts/fetch_pansgo.py --max-grade 14 --out data/raw/pansgo_k12
    # 已经手动下过原文件时，跳过网络：
    .venv/Scripts/python.exe scripts/fetch_pansgo.py --source-dir /path/to/downloaded

输出（默认 data/raw/pansgo/）：
    topics.json         数学 K12（1–14 年级）知识点
    dependencies.json   两端都在范围内的先修边
    questions.json      指向这些知识点的题目
    manifest.json       来源、提交、许可证、计数与文件 sha256

数据许可：CC BY-NC 4.0，仅限非商业用途，须署名原作者。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import pansgo  # noqa: E402

DATA_FILES = ("topics.json", "dependencies.json", "questions.json")
RAW_URL = "https://raw.githubusercontent.com/xiaoyang111222/cn-math-taxonomy/{ref}/data/{name}"


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _download(ref: str, name: str, timeout: int = 120) -> bytes:
    url = RAW_URL.format(ref=ref, name=name)
    req = urllib.request.Request(url, headers={"User-Agent": "ikgr-fetch-pansgo/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if len(data) < 2:
        raise RuntimeError(f"下载内容为空: {url}")
    return data


def _read_source(source_dir: Path | None, ref: str, name: str) -> bytes:
    if source_dir is not None:
        path = source_dir / name
        if not path.exists():
            raise FileNotFoundError(f"缺少源文件: {path}")
        return path.read_bytes()
    return _download(ref, name)


def _loads(data: bytes, name: str):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{name} 不是合法的 UTF-8 JSON: {exc}") from exc


def main() -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="下载并过滤 cn-math-taxonomy 数学 K12 数据")
    parser.add_argument("--ref", default=pansgo.SOURCE_COMMIT, help="Git 提交/分支/标签（默认锁定提交）")
    parser.add_argument("--out", default=str(ROOT / "data" / "raw" / "pansgo_k12"), help="输出目录")
    parser.add_argument("--source-dir", default=None, help="已下载的 data 目录，提供后不联网")
    parser.add_argument("--max-grade", type=int, default=pansgo.MAX_GRADE, help="最高年级（默认 14，含高中）")
    parser.add_argument("--timeout", type=int, default=120, help="单文件下载超时秒数")
    args = parser.parse_args()

    out_dir = Path(args.out)
    source_dir = Path(args.source_dir) if args.source_dir else None

    raw = {}
    for name in DATA_FILES:
        data = _read_source(source_dir, args.ref, name)
        raw[name] = _loads(data, name)
        print(f"已读取 {name}: {len(raw[name])} 条")

    filtered = pansgo.filter_math(
        raw["topics.json"],
        raw["dependencies.json"],
        raw["questions.json"],
        max_grade=args.max_grade,
    )
    errors = pansgo.validate(filtered)
    if errors:
        for error in errors[:20]:
            print(f"[错误] {error}", file=sys.stderr)
        print(f"数据校验失败，共 {len(errors)} 处问题。", file=sys.stderr)
        return 1

    files = {}
    for name, key in (
        ("topics.json", "topics"),
        ("dependencies.json", "dependencies"),
        ("questions.json", "questions"),
    ):
        path = out_dir / name
        digest = pansgo.write_json(path, filtered[key])
        files[name] = {
            "sha256": digest,
            "bytes": path.stat().st_size,
            "count": len(filtered[key]),
        }

    manifest = {
        "dataset": pansgo.DATASET_ID,
        "subject": "math",
        "grades": [1, args.max_grade],
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "repo": pansgo.SOURCE_REPO,
            "site": pansgo.SOURCE_SITE,
            "commit": args.ref,
            "files": list(DATA_FILES),
        },
        "license": pansgo.LICENSE,
        "license_url": pansgo.LICENSE_URL,
        "noncommercial": True,
        "attribution": pansgo.ATTRIBUTION,
        "filters": {
            "subject": "math (subject is null in source)",
            "grades": f"1-{args.max_grade}",
            "external": False,
            "cross_boundary_edges": "dropped (both endpoints must be in scope)",
        },
        "original_counts": {
            "topics": len(raw["topics.json"]),
            "dependencies": len(raw["dependencies.json"]),
            "questions": len(raw["questions.json"]),
        },
        "counts": {
            "topics": len(filtered["topics"]),
            "dependencies": len(filtered["dependencies"]),
            "questions": len(filtered["questions"]),
        },
        "files": files,
        "quality_note": "题目与知识点由 cn-math-taxonomy 的 AI 生成流程产出，未经一线教师审核。",
    }
    pansgo.write_json(out_dir / "manifest.json", manifest)

    print("=" * 60)
    print(f"输出目录: {out_dir}")
    print(f"知识点: {len(filtered['topics'])}  先修边: {len(filtered['dependencies'])}  题: {len(filtered['questions'])}")
    print(f"许可证: {pansgo.LICENSE}（非商业）")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
