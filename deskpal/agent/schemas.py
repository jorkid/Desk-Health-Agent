"""LangGraph 状态类型定义。

- MonitorState：监控链路（M4），外层注入外设统计与历史健康，链路产出决策。
- ChatState：对话链路（M6），累积对话消息。
"""
from typing import TypedDict, Annotated

from langgraph.graph.message import add_messages


class MonitorState(TypedDict):
    stats: dict               # 外设统计（monitor.get_stats() 的结果）
    health_context: dict      # 历史健康上下文（今日疲劳/睡眠/周报）
    actual_work_seconds: int  # 本轮真实工作时长（用户确认休息后传入）
    away_seconds: int         # 本轮中途离开工位的总时长（供休息时长判断）
    rest_seconds: int         # 本轮实际休息时长（倒计时流程得出，供下一轮时长判断）
    messages: list            # 组装后的 LLM 输入消息
    llm_raw: str              # LLM 原始输出
    decision: dict            # 解析校验后的决策


class ChatState(TypedDict):
    messages: Annotated[list, add_messages]
