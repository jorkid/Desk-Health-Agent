# -*- coding: utf-8 -*-
"""语义检索：知识库条目和查询都转成向量，算余弦相似度取 top-k。"""
import os
from pathlib import Path

from deskpal.rag.loader import load_knowledge_base, build_search_text

KB_PATH = Path(__file__).parent / "knowledge_base.json"
MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_retriever = None  # 懒加载单例：模型很重，只加载一次


def _load_model():
    """加载 embedding 模型，优先本地缓存，避免每次联网验证（国内直连 HF 会超时卡死）。"""
    from sentence_transformers import SentenceTransformer
    try:
        # ① 优先本地缓存：完全跳过联网，已下载过则秒级加载
        return SentenceTransformer(MODEL_NAME, local_files_only=True)
    except Exception:
        # ② 本地无缓存（首次部署）：联网下载，走国内镜像
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        return SentenceTransformer(MODEL_NAME)


def load_retriever():
    """加载模型，把所有条目的检索文本编码成向量。返回 (model, items, vectors)。"""
    model = _load_model()
    items = load_knowledge_base(str(KB_PATH))
    texts = [build_search_text(item) for item in items]
    vectors = model.encode(texts, normalize_embeddings=True)  # shape: (N, 维度)
    return model, items, vectors


def get_retriever():
    """懒加载单例：首次调用才加载模型，之后复用同一份。"""
    global _retriever
    if _retriever is None:
        _retriever = load_retriever()
    return _retriever


def search(model, items, vectors, query, top_k=3, threshold=0.5):
    """查询编码 -> 算相似度 -> 排序取 top-k -> 阈值过滤。

    返回 [(条目dict, 分数)]，条目是知识库里的完整 dict，方便调用方直接取载荷。
    """
    q = model.encode(query, normalize_embeddings=True)
    scores = vectors @ q
    top_idx = scores.argsort()[::-1][:top_k]
    hits = []
    for i in top_idx:
        if scores[i] >= threshold:
            hits.append((items[i], float(scores[i])))
    return hits
