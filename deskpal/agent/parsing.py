"""LLM 输出解析兜底 + 校验。

旧代码 parse_json_safely 的三层兜底（json.loads → 正则提取 → 默认值）保留，
在此基础上新增 parse_reminder_decision，对监控链路的 LLM 输出做字段级校验。
"""
import json
import re


def parse_json_safely(text) -> dict:
    """尽力把一段文本解析成 dict，失败返回空 dict（绝不抛异常）。"""
    if isinstance(text, dict):
        return text
    try:
        return json.loads(text)
    except Exception:
        pass
    # 正则提取第一层花括号 JSON（兼容 LLM 输出里夹杂说明文字的情况）
    for match in re.findall(r'\{[^{}]*\}', text or ""):
        try:
            return json.loads(match)
        except Exception:
            continue
    return {}


def parse_reminder_decision(text, default_work_duration_seconds: int) -> dict:
    """解析监控链路 LLM 输出，返回字段校验后的决策 dict（时长统一转秒）。

    校验规则：
    - condition 必须是 {疲劳, 正常, 久坐} 之一，否则回退 "疲劳"；
    - next_work_minutes（下一个工作时长，分钟）必须是正数，否则用默认工作时长；
    - suggestion 缺省给一句通用提醒。

    注意：休息时长不再由 LLM 输出，改由运行时倒计时流程决定（用户自主）。
    """
    data = parse_json_safely(text)
    condition = data.get("condition", "疲劳")
    if condition not in ("疲劳", "正常", "久坐"):
        condition = "疲劳"
    suggestion = data.get("suggestion", "请休息一下，眺望远方")

    try:
        next_work_minutes = int(data.get("next_work_minutes", default_work_duration_seconds // 60))
    except (TypeError, ValueError):
        next_work_minutes = default_work_duration_seconds // 60
    next_work_minutes = max(1, next_work_minutes)

    return {
        "condition": condition,
        "suggestion": suggestion,
        "next_work_seconds": next_work_minutes * 60,  # 下一个工作时长（秒）
    }
