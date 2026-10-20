"""运行时协调层：监控线程管理 + 双链路装配 + 优雅退出。

线程模型：
- 主线程：tkinter mainloop（UI + 弹窗轮询），通过 RuntimeManager.stop() 触发退出；
- 监控线程：可中断等待 → 采集 → 调监控图判断 → 投递弹窗 → 持久化。

关键设计：
1. 可中断 sleep（Event.wait），stop_event.set() 后立刻退出，不等满整个工作时长；
2. LLM 判断全程 try/except 降级，监控线程永不因 LLM 异常崩溃。
"""
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class RuntimeManager:
    def __init__(self, monitor, app_state, popup, repos, monitor_graph, settings):
        self.monitor = monitor
        self.app_state = app_state
        self.popup = popup
        self.repos = repos
        self.monitor_graph = monitor_graph
        self.settings = settings
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        """启动外设监听 + 监控线程。"""
        self.monitor.start()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("监控线程已启动，初始工作时长 %d 秒", self.app_state.work_duration)

    def stop(self) -> None:
        """优雅退出：置停止信号 → 等监控线程结束 → 释放监听器。"""
        logger.info("正在优雅退出...")
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.monitor.stop()
        logger.info("已退出")

    # ---- 监控线程主循环 ----
    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            work_seconds = self.app_state.work_duration
            revision = self.app_state.get_revision()
            started = time.monotonic()  # 本轮工作开始时刻
            away_total = 0.0            # 本轮中途离开工位的总时长（秒）
            # 分片等待：每 0.5 秒醒来一次；工作时长被修改则按「新时长 - 已工作」重算剩余，
            # 已工作时间不清零（这样"已工作2min改3min"会在 1min 后提醒，而非重新计时3min）
            while not self._stop_event.is_set():
                elapsed = time.monotonic() - started
                if self.app_state.get_revision() != revision:
                    work_seconds = self.app_state.work_duration
                    revision = self.app_state.get_revision()
                    logger.info("工作时长变更为 %d 秒，已工作 %.0f 秒，剩余 %.0f 秒",
                                work_seconds, elapsed, max(0.0, work_seconds - elapsed))
                if work_seconds - elapsed <= 0:
                    break  # 本轮时长用尽（含"改短到已超时"的立即触发）
                # 实时空闲检测：长时间无键鼠活动立即询问，离开工位的时间从本轮时长扣除
                if self.monitor.get_stats()["is_idle"]:
                    away = self._handle_idle()
                    if self._stop_event.is_set():
                        break
                    started += away       # 扣掉离开时长：这段时间不计入工作
                    away_total += away    # 累计离开时长，供 LLM 判断休息时长
                self._stop_event.wait(timeout=0.5)
            if self._stop_event.is_set():
                break
            self._judge_once(actual_seconds=max(1, int(round(time.monotonic() - started))),
                             current_duration=work_seconds,
                             away_seconds=int(away_total))

    def _ask_choices(self, title: str, text: str, choices, topmost: bool = False) -> int:
        """弹窗并阻塞等待用户选择，返回按钮索引；退出/点 X 关闭返回 None。"""
        result = self.popup.request_choices(title, text, choices, topmost=topmost)
        while not self._stop_event.is_set():
            if result.wait(timeout=0.5):
                break
        if self._stop_event.is_set():
            return None
        return result.choice

    def _handle_idle(self) -> float:
        """实时空闲处理：问是否离开工位。

        返回离开时长（秒），用于从本轮总工作时长扣除；未离开返回 0.0。
        """
        left = self._ask_choices(
            "工位健康管家",
            "检测到您长时间没有键鼠操作，请问是否离开了工位？",
            ["是", "不是"],
        )
        if self._stop_event.is_set():
            return 0.0

        if left == 0:
            # 离开工位：暂停计时，阻塞直到用户确认回来
            away_started = time.monotonic()
            self._ask_choices(
                "工位健康管家",
                "您已离开工位。回来后请点击确认，恢复计时。",
                ["我已回来，开始工作"],
            )
            away = time.monotonic() - away_started
            logger.info("用户离开工位 %.0f 秒，已从本轮时长扣除", away)
            return away

        # 仍在工位：询问当前状态（供后续 LLM 判断），并重置空闲计时避免重复询问
        label_idx = self._ask_choices(
            "工位健康管家", "您刚才是在工作学习，还是在放松？", ["工作学习", "放松"],
        )
        if self._stop_event.is_set():
            return 0.0
        self.app_state.idle_activity_label = "工作学习" if label_idx == 0 else "放松"
        self.monitor.mark_activity()
        return 0.0

    # ---- 单次判断：采集 → 空闲询问 → 图 → 弹窗等选择 → 按选择续期 → 持久化 ----
    # actual_seconds = 本轮实际已工作秒数；current_duration = 当前工作时长（秒）
    def _judge_once(self, actual_seconds: int, current_duration: int,
                    away_seconds: int = 0) -> None:
        stats = self.monitor.get_stats()  # 空闲询问已在 _monitor_loop 实时处理

        # ① 到点弹窗：确认休息 or 继续工作（休息时长由倒计时流程决定，不在这里给）
        work_minutes = max(1, actual_seconds // 60)
        snooze_minutes = max(1, current_duration // 60)
        choice = self._ask_choices(
            "工位健康管家",
            f"您已连续工作 {work_minutes} 分钟，该起身休息了。",
            ["确认休息", f"继续工作 {snooze_minutes} 分钟"],
            topmost=True,
        )
        if self._stop_event.is_set():
            return

        if choice == 0:
            # ② 确认休息 → 倒计时弹窗（默认时长 + 可提前结束 + 可延续）→ 拿到实际休息时长
            rest_seconds = self._run_rest_countdown(
                self.settings.default_rest_minutes * 60,
            )
            # ③ 休息完毕 → 才调 LLM，传入真实工作时长 + 中途离开时长 + 实际休息时长
            health = self._build_health_context()
            try:
                result = self.monitor_graph.invoke({
                    "stats": stats,
                    "health_context": health,
                    "actual_work_seconds": actual_seconds,
                    "away_seconds": away_seconds,
                    "rest_seconds": rest_seconds,
                })
                decision = result["decision"]
            except Exception:
                # LLM 异常降级：默认建议 + 默认工作时长，不让监控线程崩溃
                logger.exception("监控链路判断失败，降级为默认建议")
                decision = {
                    "condition": "疲劳",
                    "suggestion": "请休息一下，眺望远方",
                    "next_work_seconds": self.settings.default_work_duration_seconds,
                }
            next_work = decision["next_work_seconds"]
            logger.info("LLM 判断：真实工作=%d秒 中途离开=%d秒 实际休息=%d秒 下轮工作=%d秒",
                        actual_seconds, away_seconds, rest_seconds, next_work)
        else:
            # 「继续工作 N 分钟」或点 X 关闭 → 再工作一个当前时长，不调 LLM
            next_work = current_duration
            decision = {
                "condition": "正常",
                "suggestion": "稍后再休息",
                "next_work_seconds": next_work,
            }

        self.app_state.update_work_duration(next_work)
        self._persist(stats, decision, actual_seconds, choice)
        self.monitor.reset()

    def _run_rest_countdown(self, rest_seconds: int) -> int:
        """投递休息倒计时弹窗并阻塞等待，返回用户实际休息的总秒数。"""
        result = self.popup.request_rest_countdown("工位健康管家", rest_seconds)
        while not self._stop_event.is_set():
            if result.wait(timeout=0.5):
                break
        if self._stop_event.is_set():
            return 0
        return result.choice if result.choice is not None else 0

    def _build_health_context(self) -> dict:
        daily = self.repos["daily"]
        return {
            "fatigue": self.app_state.fatigue,
            "sleep_hours": self.app_state.sleep_hours,
            "mood": self.app_state.mood,
            "sleep_quality": self.app_state.sleep_quality,
            "weekly": daily.get_weekly(),
            "idle_activity_label": self.app_state.idle_activity_label,
        }

    def _persist(self, stats: dict, decision: dict, work_seconds: int, choice) -> None:
        daily = self.repos["daily"]
        records = self.repos.get("records")
        today = datetime.now().date().isoformat()
        current = daily.get_today()
        # 本轮工作时长精确累加（此前用采集窗口估算不准确）
        daily.upsert(
            date_str=today,
            work_seconds=current["work_seconds"] + work_seconds,
            short_breaks=current["short_breaks"] + 1,
            long_breaks=current["long_breaks"],
            fatigue=self.app_state.fatigue,
            sleep_hours=self.app_state.sleep_hours,
            suggestions=[decision["suggestion"]],
            raw_stats=stats,
        )
        if records:
            # 把用户选择与真实工作时长一并留痕，便于后续行为分析
            trace_stats = dict(stats)
            trace_stats["user_choice"] = choice
            trace_stats["work_seconds"] = work_seconds
            records.add_record(
                "reminder",
                duration_seconds=work_seconds,
                interval_seconds=decision["next_work_seconds"],
                fatigue_level=self.app_state.fatigue,
                suggestion=decision["suggestion"],
                raw_stats=trace_stats,
            )
