"""生成健康报告链路（LangGraph）：数据 + 记忆 → 动态找部位 → 追问（信息不够时）→ 调 RAG 给建议。

这是"生成健康报告" skill 的落地：用图的节点/边固化流程，用 RAG 检索表达动作。
追问循环：analyze 判断某部位信息不够 → ask 生成追问 → 用户回答后回到 analyze 重新判断。
"""
import logging
from typing import TypedDict, Annotated

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages

from deskpal.agent.parsing import parse_json_safely
from deskpal.rag.retriever import get_retriever, search
from deskpal.rag.loader import build_payload

logger = logging.getLogger(__name__)

REPORT_ANALYZE_PROMPT = (
    "你是工位健康管家。根据用户近期的健康数据、长期健康记录和已有对话，判断需要重点关注的部位。"
    "判断依据：工作时长偏长→腰/肩颈；疲劳高或睡眠差→整体疲劳；长期记录里明确提过的部位→优先。"
    "对于每个部位，若已知具体症状（如'眼睛干''腰酸'）则信息足够；"
    "若只知道部位、不知道具体感受，则信息不足，需要追问鉴别。"
    "严格输出 JSON："
    '{"parts": ["腰", "眼睛"], "needs_clarify": true, "clarify_question": "追问问题"}。'
    "parts 最多 3 个部位；needs_clarify 表示是否有部位信息不足需要追问；"
    "clarify_question 是追问用户具体感受的问题（只追问最不确定的那个部位）；"
    "若所有部位信息都足够，needs_clarify 为 false，clarify_question 为空字符串。"
    "若数据和记录都很少、无法判断任何部位，parts 输出 []、needs_clarify 为 true，"
    "clarify_question 输出主动询问的话（如：你最近有没有觉得哪里不舒服？腰、肩颈、眼睛、手腕等都可以告诉我）；"
    "只有当用户已明确表示'没有不适/都挺好'时，才输出 parts 为 []、needs_clarify 为 false。"
)

REPORT_RECOMMEND_PROMPT = (
    "你是工位健康管家。根据需要关注的部位、对应健康知识、以及用户描述的具体症状，生成健康报告。"
    "要求：\n"
    "1. 每个部位一段，用「【部位名】」开头；\n"
    "2. 先给「自测」：从该部位知识里选与用户症状最匹配的那条「症状」的「自测」字段原样引用，"
    "帮用户自己区分可能原因（可顺带说明「可能原因」）；"
    "若用户没有描述该部位具体症状，则用该部位的「鉴别问题」引导补充；\n"
    "3. 再给建议（引用「分级建议」的「轻度」，2-3 条）和预防（1-2 条）；\n"
    "4. 知识库里没有某部位时，给一句通用提醒。\n"
    "直接输出报告正文，不要输出 JSON。"
)


class ReportState(TypedDict):
    weekly: list                    # 本周健康数据（daily.get_weekly）
    facts: list                     # 长期记忆事实（memory.get_all_facts）
    messages: Annotated[list, add_messages]  # 追问对话（累积）
    focused_parts: list             # 动态判断出的关注部位
    needs_clarify: bool             # 是否有部位信息不足、需要追问
    clarify_question: str           # 待追问的问题（若有）
    report: str                     # 最终报告文本


def _last_human_text(messages) -> str:
    """取追问对话里最后一条用户消息文本（即用户对症状的描述）。"""
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage) and msg.content:
            return msg.content
    return ""


def build_report_graph(llm, app_state):
    def collect(state: ReportState) -> dict:
        """① 收集数据：读 SQL 周报 + 长期记忆（代码节点，非 LLM）。"""
        weekly = app_state.repos["daily"].get_weekly()
        facts = app_state.repos["memory"].get_all_facts()
        return {"weekly": weekly, "facts": facts}

    def analyze(state: ReportState) -> dict:
        """② 动态找部位 + 判断信息是否足够，不够则生成追问。"""
        human = (
            f"用户本周健康数据：{state['weekly']}。"
            f"用户长期健康记录：{state['facts']}。"
            f"已有对话：{state['messages']}。"
        )
        try:
            resp = llm.invoke([
                SystemMessage(content=REPORT_ANALYZE_PROMPT),
                HumanMessage(content=human),
            ])
            data = parse_json_safely(resp.content)
        except Exception:
            logger.warning("报告分析失败，返回空部位列表", exc_info=True)
            data = {}
        parts = (
            [str(p) for p in data.get("parts", []) if isinstance(p, str)][:3]
            if isinstance(data, dict) else []
        )
        needs_clarify = bool(data.get("needs_clarify", False)) if isinstance(data, dict) else False
        clarify_question = str(data.get("clarify_question", "")) if isinstance(data, dict) else ""
        if not parts:
            if not state["messages"]:
                # 首轮且无数据参考：主动追问获取初始信息（优先用 LLM 给的追问，否则默认）
                needs_clarify = True
                clarify_question = clarify_question or "你最近有没有觉得哪里不舒服？比如腰、肩颈、眼睛、手腕等，都可以告诉我。"
            else:
                # 追问过仍无部位：用户确实没有症状，结束给健康报告
                needs_clarify = False
                clarify_question = ""
        return {
            "focused_parts": parts,
            "needs_clarify": needs_clarify,
            "clarify_question": clarify_question,
        }

    def ask(state: ReportState) -> dict:
        """③ 追问：把鉴别问题作为 AI 消息加入对话，等待用户回答。"""
        return {"messages": [AIMessage(content=state["clarify_question"])]}

    def recommend(state: ReportState) -> dict:
        """④ 给建议：检索知识库载荷，交给 LLM 综合生成报告（含自测区分原因）。"""
        parts = state["focused_parts"]
        if not parts:
            return {"report": "根据目前的信息，暂未发现需要特别关注的部位。保持规律作息、定时起身活动即可。"}
        try:
            model, items, vectors = get_retriever()
        except Exception as exc:
            logger.warning("健康知识库加载失败：%s", exc)
            return {"report": "健康知识库暂不可用，请稍后再试。"}
        kb_payloads = []
        for part in parts:
            hits = search(model, items, vectors, part)
            if hits:
                kb_payloads.append(build_payload(hits[0][0]))
        user_symptom = _last_human_text(state["messages"])
        human = (
            f"关注部位：{parts}\n"
            f"用户描述的症状：{user_symptom or '（未具体描述）'}\n"
            f"健康知识库（JSON）：{kb_payloads}\n"
            "请生成健康报告。"
        )
        try:
            resp = llm.invoke([
                SystemMessage(content=REPORT_RECOMMEND_PROMPT),
                HumanMessage(content=human),
            ])
            report = resp.content.strip()
        except Exception:
            logger.warning("报告生成失败", exc_info=True)
            report = "报告生成失败，请稍后再试。"
        return {"report": report}

    def route_after_analyze(state: ReportState) -> str:
        return "ask" if state.get("needs_clarify") else "recommend"

    graph = StateGraph(ReportState)
    graph.add_node("collect", collect)
    graph.add_node("analyze", analyze)
    graph.add_node("ask", ask)
    graph.add_node("recommend", recommend)
    graph.set_entry_point("collect")
    graph.add_edge("collect", "analyze")
    graph.add_conditional_edges("analyze", route_after_analyze, {"ask": "ask", "recommend": "recommend"})
    graph.add_edge("ask", END)
    graph.add_edge("recommend", END)
    return graph.compile()
