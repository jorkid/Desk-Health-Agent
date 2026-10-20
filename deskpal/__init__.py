"""deskpal —— 工位健康管家（Workstation Health Manager）。

分层（自下而上单向依赖）：
    storage（存储）→ monitor（采集）→ agent（业务）→ ui（交互）

包名说明：现有代码 DB 文件为 deskpal.db，即英文项目名 deskpal；
避免与根目录旧文件 gwjkgj.py 同名引发 import 歧义。
"""
from deskpal.config import Settings, settings

__all__ = ["Settings", "settings"]
__version__ = "0.1.0"
