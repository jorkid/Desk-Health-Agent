"""运行时协调层：共享状态容器、运行时管理器、日志配置。"""
from deskpal.core.state import AppState
from deskpal.core.runtime import RuntimeManager
from deskpal.core.logging_setup import setup_logging
from deskpal.core.checkin import collect_daily_checkin

__all__ = ["AppState", "RuntimeManager", "setup_logging", "collect_daily_checkin"]
