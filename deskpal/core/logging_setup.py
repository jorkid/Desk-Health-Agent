"""日志配置：统一输出到 UTF-8 文件 + 控制台。

解决 Windows 控制台 GBK 编码问题：日志内容走 UTF-8 文件（中文不乱码），
控制台 handler 仅作轻量提示（避免 emoji/特殊字符引发编码错误）。
"""
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler


def _install_excepthooks() -> None:
    """全局异常钩子：把主线程/子线程的未捕获异常统一写进日志。

    价值：GUI 卡死或线程异常时不再"静默崩溃"，日志里能看到完整堆栈，
    便于定位；也避免异常线程进入不可控状态后继续拖垮进程。
    """
    logger = logging.getLogger("uncaught")

    def hook(exc_type, exc_value, exc_tb):
        logger.critical("主线程未捕获异常", exc_info=(exc_type, exc_value, exc_tb))

    def thread_hook(args):
        logger.critical("线程未捕获异常",
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = hook
    threading.excepthook = thread_hook


def setup_logging(settings) -> None:
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # 轮转：单文件 10MB、保留 3 份，防止日志无限增长耗尽磁盘
    file_handler = RotatingFileHandler(
        settings.log_file, encoding="utf-8", maxBytes=10 * 1024 * 1024, backupCount=3,
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        handlers=[file_handler, console_handler],
        force=True,
    )
    _install_excepthooks()
