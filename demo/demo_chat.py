# -*- coding: utf-8 -*-
"""最小化对话测试：真实 chat_graph + DeepSeek，验证 RAG 工具被调用并给出基于知识库的回复。"""
import sys
sys.path.insert(0, r"d:\Software\project\python\gwjkgj")
sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import SystemMessage, HumanMessage

from deskpal.config import settings
from deskpal.core import AppState
from deskpal.agent import create_llm_or_mock, make_tools, build_chat_graph
from deskpal.agent.chat_graph import SYSTEM_PROMPT

app_state = AppState(work_duration_seconds=1800, work_duration_min=600, work_duration_max=7200)
llm = create_llm_or_mock(settings)
tools = make_tools(app_state)
chat_graph = build_chat_graph(llm, tools)

question = "我的背部肌肉习惯性拉长，容易弓着影响体态"

history = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=question)]
result = chat_graph.invoke({"messages": history})

print("=== 消息流 ===")
for msg in result["messages"]:
    name = type(msg).__name__
    print(f"[{name}] {msg.content}")
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        print(f"    tool_calls: {[(c['name'], c['args']) for c in tool_calls]}")
    print()
