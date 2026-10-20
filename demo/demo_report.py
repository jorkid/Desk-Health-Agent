# -*- coding: utf-8 -*-
"""验证报告生成链路（含追问循环）：数据 + 记忆 → 动态找部位 → 信息不够则追问 → 调 RAG 给建议。"""
import os
import sys
import tempfile

sys.path.insert(0, r"d:\Software\project\python\gwjkgj")
sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import HumanMessage

from deskpal.config import settings
from deskpal.storage import Database, init_schema, DailyHealthRepo, HealthMemoryRepo
from deskpal.core import AppState
from deskpal.agent import create_llm_or_mock
from deskpal.agent.report_graph import build_report_graph

# 临时库，造长期记忆：腰 = 模糊（信息不够，触发追问），眼睛 = 明确（信息够）
db_path = os.path.join(tempfile.gettempdir(), "deskpal_report_demo.db")
if os.path.exists(db_path):
    os.remove(db_path)
db = Database(db_path)
init_schema(db)

memory = HealthMemoryRepo(db)
memory.add_fact("腰", "腰部有点不舒服", source="chat")   # 模糊 → 该触发追问
memory.add_fact("眼睛", "经常眼睛干", source="chat")      # 明确 → 无需追问

app_state = AppState(work_duration_seconds=1800, work_duration_min=600, work_duration_max=7200)
app_state.repos = {"daily": DailyHealthRepo(db), "memory": memory}
app_state.llm = create_llm_or_mock(settings)

graph = build_report_graph(app_state.llm, app_state)
print("（首次运行会加载本地 embedding 模型 + torch，约需 20~60 秒，请耐心等待，勿按 Ctrl+C）")

# ---- 首轮：判断关注部位 + 是否需要追问 ----
messages = []
result1 = graph.invoke({"messages": messages})
print("\n=== 首轮：关注部位 ===")
print(result1["focused_parts"])
print("=== 首轮：是否需要追问 ===")
print(result1["needs_clarify"], "|", result1.get("clarify_question"))

if result1["needs_clarify"]:
    # ---- 第二轮：模拟用户回答追问，重新判断 → 出报告 ----
    answer = "主要是酸痛，坐久了更明显"
    messages = list(result1["messages"])          # 保留第一轮的追问
    messages.append(HumanMessage(content=answer))  # 追加用户回答
    print(f"\n=== 用户回答：{answer} ===")
    result2 = graph.invoke({"messages": messages})
    print("\n=== 第二轮报告 ===")
    print(result2["report"])
