"""数据访问对象（DAO）：把业务语义封装在 Database 之上。

迁移说明：本文件承接旧 gwjkgj.py 中的裸函数
save_daily_summary / get_today_stats / get_weekly_summary，
逻辑保持不变，仅收拢为 Repo 类并复用线程安全的 Database。
"""
import json
from datetime import datetime, timedelta


class DailyHealthRepo:
    """每日健康汇总。"""

    def __init__(self, db):
        self.db = db

    def upsert(self, date_str, work_seconds, short_breaks, long_breaks,
               fatigue, sleep_hours, suggestions, raw_stats) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO daily_health
               (date, work_seconds, short_breaks, long_breaks, avg_fatigue,
                sleep_hours, suggestions, raw_stats)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (date_str, work_seconds, short_breaks, long_breaks, fatigue,
             sleep_hours, json.dumps(suggestions, ensure_ascii=False),
             json.dumps(raw_stats, ensure_ascii=False)),
        )

    def get_today(self) -> dict:
        today = datetime.now().date().isoformat()
        rows = self.db.query(
            "SELECT work_seconds, short_breaks, long_breaks FROM daily_health WHERE date = ?",
            (today,),
        )
        if rows:
            r = rows[0]
            return {"work_seconds": r[0], "short_breaks": r[1], "long_breaks": r[2]}
        return {"work_seconds": 0, "short_breaks": 0, "long_breaks": 0}

    def get_weekly(self, days: int = 7) -> list[dict]:
        end = datetime.now().date()
        start = end - timedelta(days=days)
        rows = self.db.query(
            """SELECT date, work_seconds, short_breaks, long_breaks, avg_fatigue, sleep_hours
               FROM daily_health WHERE date >= ? AND date <= ? ORDER BY date""",
            (start.isoformat(), end.isoformat()),
        )
        return [
            {
                "date": r[0],
                "work_minutes": r[1] // 60,
                "short_breaks": r[2],
                "long_breaks": r[3],
                "avg_fatigue": r[4],
                "sleep_hours": r[5],
            }
            for r in rows
        ]


class WorkBreakRepo:
    """工作/休息/提醒明细记录。"""

    def __init__(self, db):
        self.db = db

    def add_record(self, event_type: str, duration_seconds=None,
                   interval_seconds=None, fatigue_level=None,
                   suggestion=None, raw_stats=None) -> int:
        return self.db.execute(
            """INSERT INTO work_break_records
               (ts, event_type, duration_seconds, interval_seconds, fatigue_level, suggestion, raw_stats)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now().isoformat(), event_type, duration_seconds, interval_seconds,
             fatigue_level, suggestion,
             json.dumps(raw_stats, ensure_ascii=False) if raw_stats else None),
        )

    def get_recent(self, limit: int = 100):
        return self.db.query(
            """SELECT id, ts, event_type, duration_seconds, interval_seconds, fatigue_level, suggestion
               FROM work_break_records ORDER BY id DESC LIMIT ?""",
            (limit,),
        )


class SettingsRepo:
    """键值配置（持久化运行时状态，如 LLM 动态调整后的工作时长）。"""

    def __init__(self, db):
        self.db = db

    def get(self, key: str, default=None):
        rows = self.db.query("SELECT value FROM settings WHERE key = ?", (key,))
        if rows:
            return rows[0][0]
        return default

    def set(self, key: str, value) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )


class HealthMemoryRepo:
    """用户跨会话的健康事实（长期记忆）。

    写入走"宁滥勿缺"：提取阶段由 LLM 判断，存错了靠读取时过滤；
    按 body_part 去重（同部位更新而非追加），读取按 id 升序全量返回，供报告生成主动汇总使用。
    """

    def __init__(self, db):
        self.db = db

    def add_fact(self, body_part: str, fact: str, source: str = "chat") -> int:
        """按 body_part 去重：同部位已存在则更新事实，否则插入。

        去重依赖提取阶段的「部位名归一化」（同义说法收敛到标准名），
        因此这里用 body_part 精确匹配即可，避免同一部位反复记录越堆越多。
        """
        now = datetime.now().isoformat()
        rows = self.db.query(
            "SELECT id FROM health_memory WHERE body_part = ?", (body_part,)
        )
        if rows:
            self.db.execute(
                "UPDATE health_memory SET fact = ?, source = ?, updated_at = ? WHERE body_part = ?",
                (fact, source, now, body_part),
            )
            return rows[0][0]
        return self.db.execute(
            """INSERT INTO health_memory (body_part, fact, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (body_part, fact, source, now, now),
        )

    def get_all_facts(self) -> list[dict]:
        rows = self.db.query(
            "SELECT body_part, fact, source, updated_at FROM health_memory ORDER BY id"
        )
        return [
            {"body_part": r[0], "fact": r[1], "source": r[2], "updated_at": r[3]}
            for r in rows
        ]
