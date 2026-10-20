"""定时后台监控链路（LangGraph）：外设数据 + 历史健康 → LLM 判断 → 决策。

链路：build_context → call_llm → parse_decision
空闲判断由外层 runtime 负责（属于采集节奏，不属于图内业务）。
"""
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END

from deskpal.agent.parsing import parse_reminder_decision
from deskpal.agent.schemas import MonitorState

SYSTEM_PROMPT = (
    "你是一个工位健康管家。根据用户的外设活跃数据、历史健康数据和本轮休息情况，判断用户下一轮应该连续工作多久。"
    "严格输出 JSON："
    '{"condition": "疲劳/正常/久坐", "suggestion": "具体建议", '
    '"next_work_minutes": 建议下一轮工作时长分钟数}。'
    "next_work_minutes 是用户休息完后下一轮连续工作的时长。"
    "本轮真实工作时长越久、实际休息时长越短、疲劳度越高，next_work_minutes 应越短。"
    "如果提供了用户今日自报的心情和睡眠质量，要据此调整："
    "心情差或睡眠质量差会增加疲劳风险，应缩短 next_work_minutes；"
    "心情好且睡眠充足则可适当放长 next_work_minutes。"
    "如果提供了用户空闲时的自报状态（工作学习/放松），要据此调整："
    "自报「放松」说明用户此前并未紧张工作，可适当放长 next_work_minutes；"
    "自报「工作学习」说明用户专注投入，应按正常或更谨慎的节奏。"
    "系统还会提供本轮的真实工作时长、中途离开工位的总时长和实际休息时长："
    "真实工作越久、中途离开越少、休息越短，next_work_minutes 应越短。"
    "不要输出其他内容。"
)


def build_monitor_graph(llm, settings):
    def build_context(state: MonitorState) -> dict:
        stats = state["stats"]
        health = state["health_context"]
        actual = state.get("actual_work_seconds", 0)   # 本轮真实工作时长
        away = state.get("away_seconds", 0)            # 本轮中途离开工位总时长
        rest = state.get("rest_seconds", 0)            # 本轮实际休息时长
        weekly = health.get("weekly", [])
        idle_label = health.get("idle_activity_label")
        idle_text = (
            f"用户最近一次长时间无键鼠活动时，自报的状态是「{idle_label}」。"
            if idle_label else ""
        )
        mood = health.get("mood")
        sleep_quality = health.get("sleep_quality")
        mood_text = (
            f"用户今日自报心情「{mood}」，前夜睡眠质量「{sleep_quality}」。"
            if mood or sleep_quality else ""
        )
        human = (
            f"用户今日自评疲劳度 {health.get('fatigue', 3)}/5，睡眠 {health.get('sleep_hours', 7)} 小时。"
            f"{mood_text}"
            f"最近一周健康数据：{weekly}。"
            f"{idle_text}"
            f"过去一个采集窗口的外设数据：鼠标移动 {stats.get('mouse_dist', 0)} 像素，"
            f"键盘 {stats.get('key_count', 0)} 次，滚轮 {stats.get('scroll_count', 0)} 次，"
            f"移动事件 {stats.get('move_events', 0)} 次。"
            f"本轮真实工作时长：{max(1, actual // 60)} 分钟。"
            f"本轮中途离开工位总时长：{max(0, away // 60)} 分钟。"
            f"本轮实际休息时长：{max(0, rest // 60)} 分钟。"
        )
        return {"messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human)]}

    def call_llm(state: MonitorState) -> dict:
        response = llm.invoke(state["messages"])
        return {"llm_raw": response.content}

    def parse_decision(state: MonitorState) -> dict:
        decision = parse_reminder_decision(
            state["llm_raw"],
            settings.default_work_duration_seconds,
        )
        # 工作时长走统一安全边界 clamp（休息时长已在 parse 层 clamp 到 [1, 60] 分钟）
        decision["next_work_seconds"] = max(
            settings.work_duration_min_seconds,
            min(settings.work_duration_max_seconds, decision["next_work_seconds"]),
        )
        return {"decision": decision}

    graph = StateGraph(MonitorState)
    graph.add_node("build_context", build_context)
    graph.add_node("call_llm", call_llm)
    graph.add_node("parse_decision", parse_decision)
    graph.set_entry_point("build_context")
    graph.add_edge("build_context", "call_llm")
    graph.add_edge("call_llm", "parse_decision")
    graph.add_edge("parse_decision", END)
    return graph.compile()
