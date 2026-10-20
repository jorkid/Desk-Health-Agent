"""记忆系统：长期记忆提取 + 短期记忆窗口治理。

长期记忆（写路径）：从对话中提取用户健康事实，交给存储层持久化；
短期记忆（窗口治理）：对话消息超窗时，把最老消息滚动压缩成概况。
"""
import logging

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from deskpal.agent.parsing import parse_json_safely

logger = logging.getLogger(__name__)

EXTRACT_PROMPT = (
    "你是信息提取器。从用户这段话里，提取用户明确陈述的、关于自己身体健康的事实。"
    "每条事实包含「部位」和「事实描述」，且这些事实在未来对话中仍然有用。"
    "只提取用户明确说过的，不要推测、不要提取无关信息。"
    "「部位」请用统一简短的标准名称（腰、眼睛、颈椎、肩、手腕、膝盖、头、肠胃、睡眠、情绪），"
    "把同义说法归一（如'腰部''腰背''下背'都写'腰'，'脖子'写'颈椎'，'眼'写'眼睛'）。"
    '严格输出 JSON 数组：[{"body_part": "部位", "fact": "事实描述"}]。'
    "如果没有健康事实，输出 []。"
)


def extract_health_facts(llm, text: str) -> list[dict]:
    """用 LLM 从一段用户输入里提取健康事实，返回 [{body_part, fact}]；失败返回空列表。"""
    try:
        resp = llm.invoke([
            SystemMessage(content=EXTRACT_PROMPT),
            HumanMessage(content=text),
        ])
        data = parse_json_safely(resp.content)
    except Exception:
        logger.warning("健康事实提取失败，跳过本轮", exc_info=True)
        return []
    # 兼容 LLM 直接给数组、或包一层 {"facts": [...]} 的写法
    if isinstance(data, dict):
        data = data.get("facts") or data.get("items") or []
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        body_part = item.get("body_part") or item.get("部位")
        fact = item.get("fact") or item.get("事实")
        if body_part and fact:
            result.append({"body_part": str(body_part), "fact": str(fact)})
    return result


SUMMARY_PROMPT = (
    "你是对话压缩器。把下面这段历史对话压缩成简短概况，并与已有概况合并。"
    "概况只保留对未来对话有用的信息：用户提到过的健康问题、症状、偏好、已完成的设置变更等。"
    "去掉寒暄、客套和重复内容。用简洁中文，控制在 3 句话以内。"
    "若已有概况为空，直接生成新概况；否则把新信息合并进去，仍控制在 3 句话以内。"
)


def summarize_conversation(llm, messages, prev_summary: str = "") -> str:
    """把一段历史消息滚动压缩成概况（合并进已有概况）。失败时退回已有概况。

    只压缩用户/助手文本，跳过工具调用结果等噪音消息。
    """
    if not messages:
        return prev_summary
    lines = []
    for m in messages:
        if isinstance(m, HumanMessage) and m.content:
            lines.append(f"用户：{m.content}")
        elif isinstance(m, AIMessage) and m.content:
            lines.append(f"助手：{m.content}")
    if not lines:
        return prev_summary
    transcript = "\n".join(lines)
    try:
        resp = llm.invoke([
            SystemMessage(content=SUMMARY_PROMPT),
            HumanMessage(content=f"已有概况：{prev_summary or '（无）'}\n\n待压缩对话：\n{transcript}"),
        ])
        return resp.content.strip()
    except Exception:
        logger.warning("对话概况压缩失败，保留已有概况", exc_info=True)
        return prev_summary


def compress_window(messages, summary: str, llm, window_size: int = 10):
    """滑动窗口治理：对话消息超出窗口时，把最老的一批压缩进概况。

    返回 (保留的最近消息, 新概况)。未超窗时原样返回、不调 LLM。
    """
    if len(messages) <= window_size:
        return messages, summary
    overflow = messages[:len(messages) - window_size]
    keep = messages[len(messages) - window_size:]
    summary = summarize_conversation(llm, overflow, summary)
    return keep, summary
