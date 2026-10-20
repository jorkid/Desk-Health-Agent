# -*- coding: utf-8 -*-
"""两道防线联测：高危词表前置拦截 + 阈值过滤低分。"""
import sys
sys.path.insert(0, r"d:\Software\project\python\gwjkgj\deskpal\rag")
sys.stdout.reconfigure(encoding="utf-8")

from retriever import load_retriever, search
from safety import check_high_risk

model, items, vectors = load_retriever()


def query_pipeline(q):
    """模拟真实调用顺序：先高危词表，再检索（带阈值）。"""
    risk = check_high_risk(q)
    if risk:
        return f"[高危拦截] 命中「{risk}」→ 直接转就医，不走检索"
    hits = search(model, items, vectors, q)
    if not hits:
        return "[未覆盖] 无匹配（低于阈值 0.5），走兜底话术"
    return f"[正常] {[(it['部位'], round(s, 2)) for it, s in hits]}"


tests = ["胸闷", "心慌", "单侧无力", "膝盖疼", "耳鸣", "眼睛干", "手麻"]
for q in tests:
    print(f"{q!r:12s} -> {query_pipeline(q)}")
