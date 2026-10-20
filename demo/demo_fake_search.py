# -*- coding: utf-8 -*-
"""演示：关键词包含匹配 ≠ 语义检索。跑一遍，看哪些查询会漏召回。"""
import sys
sys.path.insert(0, r"d:\Software\project\python\gwjkgj\deskpal\rag")
sys.stdout.reconfigure(encoding="utf-8")

from loader import load_knowledge_base, build_search_text

ITEMS = load_knowledge_base(r"d:\Software\project\python\gwjkgj\deskpal\rag\knowledge_base.json")


def fake_keyword_search(query):
    """假检索：命中 = 查询里每个字都在该条目的检索文本里出现过。"""
    hits = []
    for item in ITEMS:
        text = build_search_text(item)
        if all(ch in text for ch in query):
            hits.append(f"{item['id']}({item['部位']})")
    return hits


tests = ["眼睛干", "眼睛难受", "看屏幕眼睛不舒服", "腰僵", "手麻"]
for q in tests:
    result = fake_keyword_search(q)
    print(f"查询 {q!r:18s} -> 命中 {result}")
