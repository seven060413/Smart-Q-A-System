"""文本通道：向量化知识点描述，用余弦相似度召回 Top-K。

默认使用 bge-m3 句向量（FlagEmbedding，本地 CPU 加载）。
向量化文本 = 知识点名称 + 定义/描述（见 knowledge_point_text）。
为免每次重算，可用 build_and_save_index 把向量缓存到 data/processed/。
"""

import json
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np

from .models import Node
from .subgraph import OUT_PATH, ROOT

INDEX_DIR = ROOT / "data" / "processed"


def knowledge_point_text(n: Node) -> str:
    """知识点用于向量化的文本：Concept 用 definition，Skill 用 description。"""
    if n.label == "Concept":
        desc = n.properties.get("definition", "")
    elif n.label == "Skill":
        desc = n.properties.get("description", "")
    else:
        return n.name
    return f"{n.name}：{desc}" if desc else n.name


def cosine_topk(
    query_vec, matrix, ids: Sequence[str], k: int
) -> List[Tuple[str, float]]:
    """query_vec 与 matrix 各行求余弦相似度，返回 Top-K [(id, score)]。"""
    q = np.asarray(query_vec, dtype=float).reshape(-1)
    m = np.asarray(matrix, dtype=float)
    q = q / (np.linalg.norm(q) + 1e-9)
    m = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
    sims = m @ q
    top = np.argsort(-sims)[:k]
    return [(ids[i], float(sims[i])) for i in top]


class BgeM3Embedder:
    """bge-m3 句向量封装（FlagEmbedding）。惰性加载，CPU 可跑。"""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        from FlagEmbedding import BGEM3FlagModel  # 惰性导入：未安装时不报错
        self._model = BGEM3FlagModel(model_name, use_fp16=False)

    def encode(self, texts: List[str]) -> np.ndarray:
        result = self._model.encode(
            texts,
            batch_size=8,
            max_length=512,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return np.asarray(result["dense_vecs"])


class TextRetriever:
    """文本通道检索器：向量化全部知识点，查询时余弦 Top-K 召回。"""

    def __init__(self, nodes: List[Node], embedder):
        self._embedder = embedder
        self._kp = [n for n in nodes if n.label in ("Concept", "Skill")]
        self._ids = [n.id for n in self._kp]
        self._texts = [knowledge_point_text(n) for n in self._kp]
        self._matrix = embedder.encode(self._texts)

    def retrieve(self, query: str, k: int = 3) -> List[Tuple[str, float]]:
        qv = self._embedder.encode([query])[0]
        return cosine_topk(qv, self._matrix, self._ids, k)


def build_and_save_index(
    nodes: List[Node], embedder, out_dir: Path = INDEX_DIR
) -> Tuple[np.ndarray, List[str]]:
    """向量化全部知识点并缓存到磁盘（避免每次重算）。返回 (matrix, ids)。"""
    kp = [n for n in nodes if n.label in ("Concept", "Skill")]
    ids = [n.id for n in kp]
    texts = [knowledge_point_text(n) for n in kp]
    matrix = embedder.encode(texts)
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "kp_vectors.npy", matrix.astype("float32"))
    (out_dir / "kp_ids.json").write_text(json.dumps(ids, ensure_ascii=False), encoding="utf-8")
    return matrix, ids


def load_index(out_dir: Path = INDEX_DIR) -> Tuple[np.ndarray, List[str]]:
    """从磁盘读回缓存的向量与 id。"""
    matrix = np.load(out_dir / "kp_vectors.npy")
    ids = json.loads((out_dir / "kp_ids.json").read_text(encoding="utf-8"))
    return matrix, ids


if __name__ == "__main__":
    from .loader import load_nodes
    nodes = load_nodes(OUT_PATH)
    matrix, ids = build_and_save_index(nodes, BgeM3Embedder())
    print(f"向量化完成：{len(ids)} 个知识点，维度 {matrix.shape[1]}")
