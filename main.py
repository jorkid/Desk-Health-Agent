"""入口：装配各层，启动监控线程，进入 UI 主循环。

运行：python main.py
退出：关闭聊天窗口，或 Ctrl+C（会在 finally 里优雅退出）。
"""
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from deskpal.config import settings
from deskpal.storage import Database, init_schema, DailyHealthRepo, WorkBreakRepo, SettingsRepo, HealthMemoryRepo
from deskpal.core import AppState, RuntimeManager, setup_logging, collect_daily_checkin
from deskpal.monitor import PeripheralMonitor
from deskpal.agent import (create_llm_or_mock, make_tools, build_monitor_graph,
                           build_chat_graph, build_report_graph, extract_health_facts,
                           compress_window)
from deskpal.agent.chat_graph import SYSTEM_PROMPT
from deskpal.ui import ChatApp


# 报告 skill 触发/退出意图检测（先用关键词规则，后续可升级为 LLM 意图识别）
_REPORT_INTENT_KEYWORDS = ("报告", "体检")
_REPORT_EXIT_KEYWORDS = ("取消", "算了", "不用了", "结束", "退出")


def _is_report_intent(text: str) -> bool:
    return any(k in text for k in _REPORT_INTENT_KEYWORDS)


def _is_report_exit(text: str) -> bool:
    return any(k in text for k in _REPORT_EXIT_KEYWORDS)


def build_app():
    """装配所有分层组件，返回 (app, runtime, chat_graph, app_state)。

    依赖方向：storage → monitor → agent → ui → runtime。
    """
    # 数据存储层
    db = Database(settings.db_path)
    init_schema(db)
    repos = {
        "daily": DailyHealthRepo(db),
        "records": WorkBreakRepo(db),
        "settings": SettingsRepo(db),
        "memory": HealthMemoryRepo(db),
    }

    # 共享状态（跨监控/对话链路）
    app_state = AppState(
        work_duration_seconds=settings.default_work_duration_seconds,
        work_duration_min=settings.work_duration_min_seconds,
        work_duration_max=settings.work_duration_max_seconds,
    )
    app_state.repos = repos

    # 监控采集层
    monitor = PeripheralMonitor(idle_timeout_seconds=settings.idle_timeout_seconds)

    # Agent 业务层
    llm = create_llm_or_mock(settings)
    app_state.llm = llm  # 供对话后记忆提取复用同一模型实例
    tools = make_tools(app_state)
    monitor_graph = build_monitor_graph(llm, settings)
    chat_graph = build_chat_graph(llm, tools)
    app_state.report_graph = build_report_graph(llm, app_state)  # 报告 skill 的图，供报告会话复用

    # UI 层
    app = ChatApp()

    # 运行时协调
    runtime = RuntimeManager(monitor, app_state, app.popup, repos, monitor_graph, settings)
    return app, runtime, chat_graph, app_state


def main():
    setup_logging(settings)
    app, runtime, chat_graph, app_state = build_app()
    report_graph = app_state.report_graph
    llm = app_state.llm

    # 短期记忆窗口：保留最近 N 条对话消息，更早的滚动压缩成概况
    WINDOW_SIZE = 10

    def build_system(summary):
        content = SYSTEM_PROMPT
        if summary:
            content += f"\n\n【近期对话概况】\n{summary}"
        return SystemMessage(content=content)

    def trim_history(history, summary):
        """对话消息超窗时，把最老的一批压缩进概况（原地收缩 history）。"""
        messages = history[1:]  # 去掉 system
        keep, summary = compress_window(messages, summary, llm, WINDOW_SIZE)
        history[:] = [build_system(summary)] + keep
        return summary

    # 对话会话：system（含概况）+ 窗口内消息
    summary = ""
    history = [build_system(summary)]
    # 报告会话：None 表示不在报告模式；非 None 时是 {"messages": [...]} 累积追问
    report_session = None

    def on_send(text):
        nonlocal report_session, summary
        # 长期记忆提取：对所有用户输入生效（报告追问的回答也是健康事实）
        try:
            for f in extract_health_facts(app_state.llm, text):
                app_state.repos["memory"].add_fact(f["body_part"], f["fact"], source="chat")
        except Exception:
            pass

        # 报告会话中：输入当作对追问的回答（或退出报告）
        if report_session is not None:
            if _is_report_exit(text):
                report_session = None
                app.display_message("管家", "好的，已退出报告，有什么可以帮你？")
                return
            report_session["messages"].append(HumanMessage(content=text))
            try:
                result = report_graph.invoke({"messages": report_session["messages"]})
            except Exception:
                report_session = None
                app.display_message("管家", "报告生成失败，请稍后再试。")
                return
            if result.get("needs_clarify"):
                report_session["messages"] = list(result["messages"])
                app.display_message("管家", result["clarify_question"])
            else:
                report_session = None
                app.display_message("管家", result["report"])
            return

        # 检测报告意图 → 进入报告会话
        if _is_report_intent(text):
            report_session = {"messages": []}
            try:
                result = report_graph.invoke({"messages": []})
            except Exception:
                report_session = None
                app.display_message("管家", "报告生成失败，请稍后再试。")
                return
            if result.get("needs_clarify"):
                report_session["messages"] = list(result["messages"])
                app.display_message("管家", result["clarify_question"])
            else:
                report_session = None
                app.display_message("管家", result["report"])
            return

        # 普通对话
        history.append(HumanMessage(content=text))
        try:
            result = chat_graph.invoke({"messages": history})
            history[:] = result["messages"]
        except Exception:
            history.append(AIMessage(content="抱歉，我暂时无法处理，请稍后再试。"))
        # 短期记忆窗口治理：溢出则把最老消息压缩进概况
        summary = trim_history(history, summary)
        # 显示最后一条有内容的 AI 回复
        for msg in reversed(history):
            if isinstance(msg, AIMessage) and msg.content:
                app.display_message("管家", msg.content)
                break

    app.on_send = on_send
    app.display_message("管家", "你好，我是工位健康管家。可以问我健康数据，或让我调整工作时长。")

    # 每日状态收集（心情 + 前夜睡眠质量）：启动时同步弹窗，每天一次，同天重启自动跳过
    collect_daily_checkin(app_state, app.root)

    runtime.start()
    try:
        app.run()
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
