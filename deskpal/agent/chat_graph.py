"""用户交互对话链路（LangGraph）：多轮对话 + 工具调用。

链路：chatbot ⇄ tools（有 tool_calls 时进 tools 执行，否则结束）。

与监控链路的区别：对话需要累积多轮消息，ChatState.messages 用 add_messages。
工具副作用在 M3 已真实落地，本链路只负责让 ToolNode 执行工具，
不再需要旧代码里"用正则猜 ToolMessage 改工作时长"的事后逻辑。
"""
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from deskpal.agent.schemas import ChatState

SYSTEM_PROMPT = (
    "你是工位健康管家。你可以调用工具获取用户健康数据或修改工作时长设置。"
    "根据用户的问题决定是否调用工具，并给出友好、简洁的回答。"
)


def build_chat_graph(llm, tools):
    llm_with_tools = llm.bind_tools(tools)

    def chatbot(state: ChatState) -> dict:
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(ChatState)
    graph.add_node("chatbot", chatbot)
    graph.add_node("tools", ToolNode(tools))
    graph.set_entry_point("chatbot")
    graph.add_conditional_edges("chatbot", tools_condition)
    graph.add_edge("tools", "chatbot")
    return graph.compile()
