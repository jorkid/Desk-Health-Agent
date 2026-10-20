# -*- coding: utf-8 -*-
"""验证长期记忆闭环：LLM 提取 → 写入 health_memory → 全量读取。"""
import os
import sys
import tempfile

sys.path.insert(0, r"d:\Software\project\python\gwjkgj")
sys.stdout.reconfigure(encoding="utf-8")

from deskpal.config import settings
from deskpal.storage import Database, init_schema, HealthMemoryRepo
from deskpal.agent import create_llm_or_mock
from deskpal.agent.memory import extract_health_facts

# 用临时库，避免污染真实数据库
db_path = os.path.join(tempfile.gettempdir(), "deskpal_memory_demo.db")
if os.path.exists(db_path):
    os.remove(db_path)

db = Database(db_path)
init_schema(db)
repo = HealthMemoryRepo(db)
llm = create_llm_or_mock(settings)

# 模拟用户的一句话（含多个部位的健康事实）
text = "我最近腰有点酸，坐久了更明显，眼睛也经常干。"
print("=== 用户输入 ===")
print(text)

facts = extract_health_facts(llm, text)
print("\n=== LLM 提取结果 ===")
print(facts)

for f in facts:
    repo.add_fact(f["body_part"], f["fact"], source="chat")

print("\n=== 写入后全量读取 ===")
for item in repo.get_all_facts():
    print(item)
