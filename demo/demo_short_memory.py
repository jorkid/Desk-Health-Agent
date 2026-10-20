# -*- coding: utf-8 -*-
"""验证短期记忆窗口治理：多轮对话超窗后，最老消息被滚动压缩成概况。"""
import sys

sys.path.insert(0, r"d:\Software\project\python\gwjkgj")
sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import HumanMessage, AIMessage

from deskpal.config import settings
from deskpal.agent import create_llm_or_mock
from deskpal.agent.memory import compress_window

llm = create_llm_or_mock(settings)

# 模拟一段对话：用户透露眼睛干、腰酸，并把工作时长改成 25 分钟
conversation = [
    HumanMessage(content="我最近眼睛有点干"),
    AIMessage(content="建议每 20 分钟远眺 20 秒，多眨眼。"),
    HumanMessage(content="腰也有点酸，坐久了"),
    AIMessage(content="建议每 45 分钟起身活动，做腰部转体。"),
    HumanMessage(content="帮我把工作时长改成 25 分钟"),
    AIMessage(content="好的，已调整为 25 分钟。"),
]

# window_size=4 触发压缩：最老 2 条（眼睛干）被压进概况，保留最近 4 条
keep, summary = compress_window(conversation, "", llm, window_size=4)

print("=== 压缩后保留的最近消息 ===")
for m in keep:
    print(f"[{type(m).__name__}] {m.content}")
print("\n=== 滚动概况（压缩掉的最老消息）===")
print(summary)
