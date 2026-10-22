"""核验 K12-KGraph 开源数据集的真实结构。

用途：回答「数据集里到底有几种节点、几种关系、多少条数据」。
只用标准库，无需额外安装依赖。

用法（在项目根目录）：
    python scripts/verify_dataset.py

输出：原始数据的实测统计，可与 HuggingFace 数据卡片 / 论文描述对照。
"""

import collections
import json
import sys
import urllib.request
from datetime import datetime

HF_REPO = "lhpku20010120/K12-KGraph"
HF_API = f"https://huggingface.co/api/datasets/{HF_REPO}"
HF_RESOLVE = f"https://huggingface.co/datasets/{HF_REPO}/resolve/main"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"

# 数据集内各学科图谱文件
SUBJECT_FILES = {
    "math": "K12-KGraph/subject_specific_KG/math.json",
    "physics": "K12-KGraph/subject_specific_KG/physics.json",
    "chemistry": "K12-KGraph/subject_specific_KG/chemistry.json",
    "biology": "K12-KGraph/subject_specific_KG/biology.json",
}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def section(title: str) -> None:
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def count_types(items, key: str):
    return collections.Counter(
        (i.get(key) if isinstance(i, dict) else None) for i in items
    )


def main() -> None:
    print(f"核验时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"数据集仓库: https://huggingface.co/datasets/{HF_REPO}")

    # ---------- 1. 仓库元信息（判断是否为最新版本） ----------
    section("1. 仓库元信息（确认你取到的是最新版）")
    try:
        meta = fetch_json(HF_API)
        print(f"最后更新时间: {meta.get('lastModified')}")
        print(f"下载量: {meta.get('downloads')}")
        print(f"点赞数: {meta.get('likes')}")
        print(f"授权标签: {meta.get('cardData', {}).get('license')}")
        files = [s.get("rfilename") for s in meta.get("siblings", [])]
        print(f"仓库文件数: {len(files)}")
        kg_files = [f for f in files if f.startswith("K12-KGraph/")]
        print("图谱相关文件:")
        for f in sorted(kg_files)[:20]:
            print("   ", f)
    except Exception as e:
        print(f"[跳过] 元信息获取失败: {e}")

    # ---------- 2. 全局图谱：节点与关系类型 ----------
    section("2. 全局图谱 global_KG（最权威的类型统计）")
    try:
        nodes = fetch_json(f"{HF_RESOLVE}/K12-KGraph/global_KG/nodes.json")
        edges = fetch_json(f"{HF_RESOLVE}/K12-KGraph/global_KG/edges.json")
        if isinstance(nodes, dict):
            nodes = next(v for v in nodes.values() if isinstance(v, list))
        if isinstance(edges, dict):
            edges = next(v for v in edges.values() if isinstance(v, list))

        print(f"节点总数: {len(nodes)}")
        print(f"边总数: {len(edges)}")

        labels = count_types(nodes, "label")
        print(f"\n节点类型数量: {len(labels)}")
        for k, v in labels.most_common():
            print(f"   {k}: {v}")

        etypes = count_types(edges, "type")
        print(f"\n关系类型数量: {len(etypes)}")
        for k, v in etypes.most_common():
            print(f"   {k}: {v}")

        print("\n节点字段:", list(nodes[0].keys()) if nodes else "无")
        print("边字段:", list(edges[0].keys()) if edges else "无")
    except Exception as e:
        print(f"[失败] 全局图谱获取失败: {e}")

    # ---------- 3. 各学科图谱规模 ----------
    section("3. 各学科图谱规模（subject_specific_KG）")
    for subject, path in SUBJECT_FILES.items():
        try:
            data = fetch_json(f"{HF_RESOLVE}/{path}")
            n = len(data.get("nodes", []))
            e = len(data.get("edges", []))
            labels = count_types(data.get("nodes", []), "label")
            types_desc = "、".join(f"{k}({v})" for k, v in labels.most_common())
            print(f"{subject:9s}: 节点 {n:5d}  边 {e:5d}   [{types_desc}]")
        except Exception as ex:
            print(f"{subject:9s}: [失败] {ex}")

    section("核验完成")
    print("对照方法：")
    print("  - HuggingFace 数据卡片 -> 应声明节点/关系类型数")
    print("  - GitHub README        -> 应列出 schema（类型名称）")
    print("  - arXiv 论文           -> 可能描述更完整的理论 schema")
    print("若三者不一致，以【实际下载数据的统计结果】为准，并注明差异。")


if __name__ == "__main__":
    sys.exit(main())
