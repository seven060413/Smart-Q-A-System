"""浏览器辅助采集：按知识点搜索 B 站，写入待审候选。

为什么不用 B 站搜索 API：
- 匿名请求常返回风控占位（v_voucher），没有结果；
- 用真实浏览器打开 search.bilibili.com 可以正常渲染结果。

本脚本用 Chrome/Edge headless 打开搜索页、解析 HTML，只写
video_candidates（待审），不会自动 approved。之后用
scripts/review_videos.py 审核，审核时再用 --fetch-meta 补齐 aid/cid。

用法（项目根目录）：
    # 只采几个知识点
    .venv/Scripts/python.exe scripts/collect_videos_browser.py \
        --node-key math_5b_rjb_cpt20 --node-key math_5b_rjb_cpt18

    # 采五年级下册全部 59 个知识点（较慢，注意限速）
    .venv/Scripts/python.exe scripts/collect_videos_browser.py --all-5b

    # 只看会搜什么，不写库
    .venv/Scripts/python.exe scripts/collect_videos_browser.py --all-5b --dry-run
"""

from __future__ import annotations

import argparse
import html as html_lib
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db as db_module  # noqa: E402
from src.loader import load_nodes  # noqa: E402
from src.subgraph import OUT_PATH  # noqa: E402
from src.video_import import (  # noqa: E402
    DEFAULT_COURSE_ID,
    parse_duration,
    upsert_candidate,
)

BOOK_VERSION_ID = "math:book:math_5b_rjb"
RAW_DIR = ROOT / "data" / "app" / "browser_search"
CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_CARD_RE = re.compile(
    r'<a href="//www\.bilibili\.com/video/(BV[0-9A-Za-z]{10})/"[^>]*'
    r'data-mod="search-card"[^>]*>(.*?)(?=<a href="//www\.bilibili\.com/video/BV|$)',
    re.S,
)
_TITLE_RE = re.compile(
    r'bili-video-card__info--tit"[^>]*title="([^"]*)"'
)
_DURATION_RE = re.compile(
    r'bili-video-card__stats__duration"[^>]*>([^<]+)</span>'
)
_OWNER_RE = re.compile(
    r'bili-video-card__info--owner"[^>]*>(.*?)</a>', re.S
)


def _configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _find_browser(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
        raise SystemExit(f"找不到浏览器: {path}")
    for path in CHROME_CANDIDATES:
        if path.exists():
            return path
    raise SystemExit("未找到 Chrome/Edge，请用 --chrome 指定浏览器路径")


def _search_html(browser: Path, keyword: str, timeout: int) -> str:
    url = "https://search.bilibili.com/all?keyword=" + urllib.parse.quote(
        keyword
    )
    profile = tempfile.mkdtemp(prefix="ikgr-bili-search-")
    cmd = [
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        f"--user-data-dir={profile}",
        f"--user-agent={USER_AGENT}",
        "--virtual-time-budget=12000",
        "--dump-dom",
        url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=timeout,
        )
    finally:
        # Windows 下 Chrome 可能短暂占用 profile，忽略清理失败。
        import shutil

        shutil.rmtree(profile, ignore_errors=True)

    if not result.stdout:
        raise RuntimeError(
            (result.stderr or "").strip()[:300] or "浏览器没有返回页面"
        )
    return result.stdout


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", html_lib.unescape(text or "")).strip()


def parse_results(raw: str) -> list[dict]:
    """从搜索页 DOM 中解析 BV、标题、时长、UP 主，按 BV 去重。"""
    results: list[dict] = []
    seen: set[str] = set()
    for match in _CARD_RE.finditer(raw):
        bvid = match.group(1)
        if bvid in seen:
            continue
        body = match.group(2)
        title_match = _TITLE_RE.search(body)
        if title_match is None:
            continue
        title = _clean(title_match.group(1))
        if not title:
            continue
        duration_match = _DURATION_RE.search(body)
        owner_match = _OWNER_RE.search(body)
        results.append(
            {
                "bvid": bvid,
                "title": title,
                "duration_seconds": parse_duration(
                    duration_match.group(1) if duration_match else None
                ),
                "author": _clean(owner_match.group(1)) if owner_match else None,
            }
        )
        seen.add(bvid)
    return results


def _select_nodes(args) -> list:
    nodes = [
        n for n in load_nodes(OUT_PATH) if n.label in ("Concept", "Skill")
    ]
    if args.node_key:
        wanted = set(args.node_key)
        unknown = wanted - {n.id for n in nodes}
        if unknown:
            print(f"[警告] 不在五年级下册子图中的节点: {sorted(unknown)}")
        nodes = [n for n in nodes if n.id in wanted]
    elif not args.all_5b:
        raise SystemExit("请用 --node-key 指定知识点，或使用 --all-5b")
    return nodes


def main() -> None:
    _configure_stdout()
    parser = argparse.ArgumentParser(description="浏览器辅助采集 B 站视频候选")
    parser.add_argument("--db", dest="db_path", default=None)
    parser.add_argument("--node-key", dest="node_key", action="append", default=None)
    parser.add_argument("--all-5b", action="store_true", help="采集五年级下册全部 Concept/Skill")
    parser.add_argument("--suffix", default="五年级 数学", help="搜索词后缀")
    parser.add_argument("--per-node", type=int, default=5, help="每个知识点保留前几条")
    parser.add_argument("--interval", type=float, default=3.0, help="两次搜索间隔秒数")
    parser.add_argument("--timeout", type=int, default=60, help="单次浏览器超时秒数")
    parser.add_argument("--chrome", default=None, help="Chrome/Edge 可执行文件路径")
    parser.add_argument("--course-id", default=DEFAULT_COURSE_ID)
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = parser.parse_args()

    nodes = _select_nodes(args)
    if not nodes:
        print("没有匹配的知识点。")
        return

    browser = _find_browser(args.chrome)
    print(f"浏览器: {browser}")
    print(f"待采集知识点: {len(nodes)} 个")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = None if args.dry_run else db_module.connect(args.db_path)
    total = 0

    try:
        for index, node in enumerate(nodes, start=1):
            keyword = f"{node.name} {args.suffix}".strip()
            print(f"[{index}/{len(nodes)}] {node.id} {node.name} -> 搜索: {keyword}")
            try:
                raw = _search_html(browser, keyword, args.timeout)
            except Exception as exc:
                print(f"  [跳过] 搜索失败: {exc}")
                continue

            raw_path = RAW_DIR / f"{node.id}.html"
            raw_path.write_text(raw, encoding="utf-8")
            results = parse_results(raw)[: max(1, args.per_node)]
            if not results:
                print("  [跳过] 没有解析到结果（可能触发风控/验证）")
                continue

            for rank, item in enumerate(results, start=1):
                line = (
                    f"  {rank}. {item['bvid']} "
                    f"{item['duration_seconds'] or '-'} "
                    f"{item['title'][:70]} | {item['author'] or '-'}"
                )
                if args.dry_run:
                    print(line)
                    continue
                candidate_id = upsert_candidate(
                    conn,
                    node_key=node.id,
                    bvid=item["bvid"],
                    query=f"browser:{keyword}",
                    page=1,
                    title=item["title"],
                    author=item["author"],
                    duration_seconds=item["duration_seconds"],
                    search_rank=rank,
                    raw={
                        "source": "browser-search",
                        "keyword": keyword,
                        "raw_path": str(raw_path),
                    },
                    course_id=args.course_id,
                )
                total += 1
                print(f"  candidate={candidate_id} {line.strip()}")

            if conn is not None:
                conn.commit()
            if index < len(nodes):
                time.sleep(max(0.0, args.interval))
    finally:
        if conn is not None:
            conn.close()

    if args.dry_run:
        print("dry-run 完成，未写库。")
    else:
        print(f"采集完成，写入/更新候选 {total} 条。")
        print("下一步: review_videos.py list --status pending")
        print("审核通过时加 --fetch-meta 补齐 aid/cid。")


if __name__ == "__main__":
    main()
