# -*- coding: utf-8 -*-
"""验证：① 记忆去重（同部位更新而非追加） ② 无数据首轮主动追问。"""
import os
import sys
import tempfile

sys.path.insert(0, r"d:\Software\project\python\gwjkgj")
sys.stdout.reconfigure(encoding="utf-8")

from deskpal.config import settings
from deskpal.storage import Database, init_schema, DailyHealthRepo, HealthMemoryRepo
from deskpal.core import AppState
from deskpal.agent import create_llm_or_mock
from deskpal.agent.report_graph import build_report_graph

db_path = os.path.join(tempfile.gettempdir(), "deskpal_dedup_demo.db")
if os.path.exists(db_path):
    os.remove(db_path)
db = Database(db_path)
init_schema(db)
memory = HealthMemoryRepo(db)

# ① 记忆去重：同部位写两次 → 只保留最新一条
memory.add_fact("腰", "有点不舒服")
memory.add_fact("腰", "经常酸痛")
facts = memory.get_all_facts()
print("=== ① 去重后记忆 ===")
for f in facts:
    print(f["body_part"], "->", f["fact"])
assert len(facts) == 1 and facts[0]["fact"] == "经常酸痛", f"去重失败：{facts}"
print("去重 OK：同部位只保留一条最新事实\n")

# ② 无数据首轮：全新空库（无 daily 数据、无 memory）→ 应主动追问
db_path2 = os.path.join(tempfile.gettempdir(), "deskpal_empty_demo.db")
if os.path.exists(db_path2):
    os.remove(db_path2)
db2 = Database(db_path2)
init_schema(db2)

app_state = AppState()
app_state.repos = {"daily": DailyHealthRepo(db2), "memory": HealthMemoryRepo(db2)}
app_state.llm = create_llm_or_mock(settings)
graph = build_report_graph(app_state.llm, app_state)
result = graph.invoke({"messages": []})
print("=== ② 无数据首轮 ===")
print("关注部位：", result["focused_parts"])
print("需要追问：", result["needs_clarify"])
print("追问内容：", result.get("clarify_question"))
