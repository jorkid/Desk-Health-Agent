# -*- coding: utf-8 -*-
"""测一批边界 query 的 top-3 分数，用来决定相似度阈值设在哪。"""
import sys
sys.path.insert(0, r"d:\Software\project\python\gwjkgj\deskpal\rag")
sys.stdout.reconfigure(encoding="utf-8")

from retriever import load_retriever, search

model, items, vectors = load_retriever()

# 分三类：
#   A 正常命中（应该高分）
#   B 覆盖边缘（健康问题，但知识库只有相近部位）
#   C 健康问题但知识库完全没覆盖
queries = [
    ("A", "眼睛干"),
    ("A", "手麻"),
    ("A", "脖子僵硬"),
    ("B", "膝盖疼"),
    ("B", "手腕疼"),
    ("B", "脚麻"),
    ("C", "耳鸣"),
    ("C", "胸闷"),
]

for kind, q in queries:
    hits = search(model, items, vectors, q)
    print(f"[{kind}] {q!r:12s} -> {[(it['部位'], round(s, 2)) for it, s in hits]}")
