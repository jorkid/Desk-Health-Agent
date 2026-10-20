# -*- coding: utf-8 -*-
"""直接测 search_health_knowledge_tool 工具函数（不经 LLM），验证三道防线在工具内的落地。"""
import sys
sys.path.insert(0, r"d:\Software\project\python\gwjkgj")
sys.stdout.reconfigure(encoding="utf-8")

from deskpal.agent.tools import make_tools
from deskpal.core import AppState

app_state = AppState(work_duration_seconds=1800, work_duration_min=600, work_duration_max=7200)
tools = make_tools(app_state)
tool = tools[2]  # search_health_knowledge_tool


def call(tool, *args):
    if hasattr(tool, "func"):
        return tool.func(*args)
    return tool.invoke(*args)


tests = ["胸闷", "眼睛干", "耳鸣"]
for q in tests:
    print(f"=== 查询 {q!r} ===")
    print(call(tool, q))
    print()
