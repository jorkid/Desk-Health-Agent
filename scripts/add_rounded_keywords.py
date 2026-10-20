# -*- coding: utf-8 -*-
"""一次性：给圆肩驼背条目补口语别名「弓背」「弓着」。"""
import json

KB_PATH = r"d:\Software\project\python\gwjkgj\deskpal\rag\knowledge_base.json"

with open(KB_PATH, encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    if item["id"] == "rounded_shoulder":
        for word in ("弓背", "弓着"):
            if word not in item["部位别名"]:
                item["部位别名"].append(word)
        print("补词后别名:", item["部位别名"])

with open(KB_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("已写回")
