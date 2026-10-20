"""Agent 工具系统：内置三个工具，副作用真实落地。

设计要点：
1. 工厂函数 make_tools(app_state) 通过闭包注入共享状态，工具内部直接读写真实状态
   （修复旧代码"工具只返回 JSON、改状态靠正则猜"的缺陷）；
2. 工具返回统一 JSON 结构 {"status": "success"/"error", ...}，便于 LLM 与代码判断；
3. 参数做防御性校验（LLM 可能传字符串/负数/浮点数），非法输入返回结构化 error 不抛异常。
"""
import json
import logging

from langchain_core.tools import tool

from deskpal.rag.loader import build_payload
from deskpal.rag.retriever import get_retriever, search
from deskpal.rag.safety import check_high_risk

logger = logging.getLogger(__name__)


def make_tools(app_state):
    @tool
    def get_weekly_summary_tool() -> str:
        """获取用户最近一周的健康数据汇总（工作分钟、休息次数、平均疲劳度、睡眠时长）。"""
        if app_state.repos is None:
            return json.dumps({"status": "error", "message": "数据层未初始化"}, ensure_ascii=False)
        weekly = app_state.repos["daily"].get_weekly()
        return json.dumps(weekly, ensure_ascii=False)

    @tool
    def update_work_duration(new_work_duration: int) -> str:
        """修改工作时长（单位分钟）。工作时长指用户连续工作多久后提醒休息。传入新的工作时长分钟数。"""
        try:
            new_work_duration = int(new_work_duration)
        except (TypeError, ValueError):
            return json.dumps({"status": "error", "message": "工作时长必须为整数"}, ensure_ascii=False)
        if new_work_duration <= 0:
            return json.dumps({"status": "error", "message": "工作时长必须为正整数"}, ensure_ascii=False)

        # 内部以秒存储，分钟 × 60 换算后走统一安全边界 clamp
        actual = app_state.update_work_duration(new_work_duration * 60)
        actual_minutes = actual // 60
        logger.info("工具 update_work_duration 落地：请求 %s 分钟 → 实际生效 %s 分钟",
                    new_work_duration, actual_minutes)
        if actual_minutes != new_work_duration:
            return json.dumps(
                {"status": "success", "work_duration_minutes": actual_minutes,
                 "note": f"已按安全边界调整到 {actual_minutes} 分钟"},
                ensure_ascii=False,
            )
        return json.dumps(
            {"status": "success", "work_duration_minutes": actual_minutes},
            ensure_ascii=False,
        )

    @tool
    def search_health_knowledge_tool(query: str) -> str:
        """当用户描述身体某个部位不适、想了解可能原因和缓解建议时调用。传入用户的症状描述文本（如"眼睛干""膝盖疼"）。"""
        # ① 高危词表前置拦截：命中直接转就医，不进检索
        risk = check_high_risk(query)
        if risk:
            return json.dumps(
                {"status": "high_risk",
                 "message": f"检测到高危信号「{risk}」，建议尽快就医，暂不提供居家缓解建议。"},
                ensure_ascii=False,
            )

        # ② 语义检索（懒加载模型，失败降级）
        try:
            model, items, vectors = get_retriever()
        except Exception as exc:
            logger.warning("健康知识库加载失败：%s", exc)
            return json.dumps({"status": "error", "message": "健康知识库暂不可用"}, ensure_ascii=False)

        hits = search(model, items, vectors, query)
        if not hits:
            return json.dumps(
                {"status": "not_found",
                 "message": "没有匹配到明确的部位，请再具体描述一下不适的位置和感觉。"},
                ensure_ascii=False,
            )

        # ③ 取 top-1 完整载荷，附带检索置信度
        item, score = hits[0]
        payload = build_payload(item)
        payload["_score"] = round(score, 3)
        return json.dumps(payload, ensure_ascii=False)

    return [get_weekly_summary_tool, update_work_duration, search_health_knowledge_tool]
