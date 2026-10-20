"""建表 SQL 与幂等初始化。

四张表：
- daily_health：每日健康汇总（沿用旧代码，字段保留并补默认值）
- work_break_records：工作/休息/提醒明细（新增，供周报与历史分析）
- settings：键值配置（新增，持久化运行时状态如动态间隔）
- health_memory：用户跨会话健康事实（长期记忆，供报告生成/主动关心使用）
"""

DAILY_HEALTH_TABLE = """
CREATE TABLE IF NOT EXISTS daily_health (
    date TEXT PRIMARY KEY,
    work_seconds INTEGER NOT NULL DEFAULT 0,
    short_breaks INTEGER NOT NULL DEFAULT 0,
    long_breaks INTEGER NOT NULL DEFAULT 0,
    avg_fatigue REAL,
    sleep_hours REAL,
    suggestions TEXT,
    raw_stats TEXT
)
"""

WORK_BREAK_TABLE = """
CREATE TABLE IF NOT EXISTS work_break_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    duration_seconds INTEGER,
    interval_seconds INTEGER,
    fatigue_level INTEGER,
    suggestion TEXT,
    raw_stats TEXT
)
"""

SETTINGS_TABLE = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
"""

HEALTH_MEMORY_TABLE = """
CREATE TABLE IF NOT EXISTS health_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body_part TEXT NOT NULL,
    fact TEXT NOT NULL,
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

ALL_TABLES = [DAILY_HEALTH_TABLE, WORK_BREAK_TABLE, SETTINGS_TABLE, HEALTH_MEMORY_TABLE]


def init_schema(db) -> None:
    """幂等初始化所有表，可重复调用。"""
    for stmt in ALL_TABLES:
        db.execute(stmt)
