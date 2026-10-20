# -*- coding: utf-8 -*-
"""诊断：定位"弓着影响体态"为什么偏到腰椎。"""
import sys
sys.path.insert(0, r"d:\Software\project\python\gwjkgj")
sys.stdout.reconfigure(encoding="utf-8")

from deskpal.rag.retriever import get_retriever, search

model, items, vectors = get_retriever()

queries = [
    "弓背",
    "圆肩",
    "含胸驼背",
    "体态",
    "背部",
    "背部肌肉拉长弓着",
    "弓着影响体态",
    "我的背部肌肉习惯性拉长，容易弓着影响体态",
]
for q in queries:
    hits = search(model, items, vectors, q)
    print(f"{q!r:34s} -> {[(it['部位'], round(s, 2)) for it, s in hits]}")
