"""每日状态收集：启动时收集心情 + 前夜睡眠质量，每天一次（去重）。

设计要点：
1. 去重标记存在 settings 表 last_checkin_date 键，值为 ISO 日期字符串；
2. 同一天重启不重复收集，但从 settings 恢复已收集的标签到 AppState；
3. 弹窗用 ask_choice_sync 同步收集（启动时主线程、mainloop 之前）。
"""
import logging
from datetime import datetime

from deskpal.ui.popup import ask_choice_sync

logger = logging.getLogger(__name__)

MOOD_CHOICES = ["很好", "不错", "一般", "较差"]
SLEEP_CHOICES = ["很好", "一般", "较差"]

LAST_CHECKIN_KEY = "last_checkin_date"
MOOD_KEY = "mood"
SLEEP_KEY = "sleep_quality"


def collect_daily_checkin(app_state, root) -> None:
    """启动时调用：恢复/收集当天心情与睡眠质量（每天一次）。

    逻辑：
    - 先读 settings 恢复当天已收集的标签到 app_state；
    - 若 last_checkin_date == 今天，跳过弹窗（同天重开不重复收集）；
    - 否则弹窗依次收集心情、睡眠质量，写入 settings 与 app_state。
    """
    settings_repo = app_state.repos["settings"]
    today = datetime.now().date().isoformat()

    # 恢复上次收集的标签（空串/缺失都归一为 None）
    app_state.mood = settings_repo.get(MOOD_KEY) or None
    app_state.sleep_quality = settings_repo.get(SLEEP_KEY) or None

    if settings_repo.get(LAST_CHECKIN_KEY) == today:
        logger.info("今日状态已收集，跳过（心情=%s 睡眠=%s）",
                    app_state.mood, app_state.sleep_quality)
        return

    mood = ask_choice_sync(root, "工位健康管家", "请问您今天的心情如何？", MOOD_CHOICES)
    sleep = ask_choice_sync(root, "工位健康管家", "请问您昨晚的睡眠质量如何？", SLEEP_CHOICES)

    app_state.mood = mood
    app_state.sleep_quality = sleep
    settings_repo.set(LAST_CHECKIN_KEY, today)
    settings_repo.set(MOOD_KEY, mood or "")
    settings_repo.set(SLEEP_KEY, sleep or "")
    logger.info("今日状态已收集：心情=%s 睡眠=%s", mood, sleep)
