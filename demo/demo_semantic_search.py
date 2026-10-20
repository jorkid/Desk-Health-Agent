# -*- coding: utf-8 -*-
"""语义检索 vs 关键词检索：同一批查询，看谁漏召回。"""
import sys
sys.path.insert(0, r"d:\Software\project\python\gwjkgj\deskpal\rag")
sys.stdout.reconfigure(encoding="utf-8")

from retriever import load_retriever, search

model, items, vectors = load_retriever()   # 首次会下载模型，慢 / 可能报网络错

tests = ["眼睛干", "眼睛难受", "看屏幕眼睛不舒服", "腰僵", "手麻"]
for q in tests:
    hits = search(model, items, vectors, q)
    print(f"查询 {q!r:18s} -> {[(it['部位'], round(s, 2)) for it, s in hits]}")
