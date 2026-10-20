"""配置中心：集中管理所有可调参数，禁止在业务代码里散落魔法数字。

设计原则：
1. 密钥（API Key）只从环境变量读取，绝不硬编码进源码或提交到仓库；
2. 默认值仅作"冷启动兜底"，不是业务逻辑的硬编码（时长边界见 WORK_DURATION_*）；
3. 用 dataclass 组织，便于测试时注入不同配置（如 DB 用 :memory:）；
4. 关键项支持环境变量覆盖，部署时无需改代码。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_str(key: str, default: str) -> str:
    """读字符串环境变量，未设置时返回默认值。"""
    return os.getenv(key, default)


def _load_dotenv() -> None:
    """轻量加载项目根目录 .env 文件（不引入 python-dotenv 依赖）。

    仅在环境变量未设置时覆盖（环境变量优先级更高）。
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    # ---- 模型接入（统一接口：provider / 模型名 / key / base_url 均可配置）----
    # LLM_PROVIDER：模型提供商，deepseek / openai / google_genai / anthropic 等
    llm_provider: str = field(default_factory=lambda: _env_str("LLM_PROVIDER", "deepseek"))
    # LLM_API_KEY：API Key（对应 LLM_PROVIDER 选中的提供商）
    api_key: str = field(default_factory=lambda: _env_str("LLM_API_KEY", ""))
    # flash：日常判断、低成本；pro：复杂重构时切换（模型名为 provider 专属）
    llm_model_flash: str = field(default_factory=lambda: _env_str("LLM_MODEL_FLASH", "deepseek-v4-flash"))
    llm_model_pro: str = field(default_factory=lambda: _env_str("LLM_MODEL_PRO", "deepseek-v4-pro"))
    # 空串表示用 LangChain 默认 base_url；OpenAI 兼容端点（豆包/火山引擎）需覆盖
    llm_base_url: str = field(default_factory=lambda: _env_str("LLM_BASE_URL", ""))
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 30.0   # 单次 LLM 调用超时，超时走降级
    llm_max_retries: int = 2            # 网络错误重试次数

    # ---- 数据存储 ----
    db_path: str = field(default_factory=lambda: _env_str("DB_PATH", "deskpal.db"))

    # ---- 外设监控 ----
    stats_window_seconds: int = 30    # 每次判断的采集窗口（秒）
    idle_timeout_seconds: int = 300   # 多久无操作判为空闲（秒）：超过则询问是否离开工位

    # ---- 工作时长（LLM 建议值 + 安全边界）----
    default_work_duration_seconds: int = 1800  # 初始工作时长（30 分钟），冷启动兜底
    work_duration_min_seconds: int = 300       # 安全下界（5 分钟）：防 LLM 幻觉给几秒疯狂弹窗
    work_duration_max_seconds: int = 7200      # 安全上界（2 小时）：久坐极限，防 LLM 给 10 小时永不提醒
    default_rest_minutes: int = 10             # 休息倒计时默认时长（分钟），确认休息后倒计时从此起算

    # ---- UI ----
    popup_poll_ms: int = 200  # 主线程轮询弹窗队列的周期（毫秒）

    # ---- 日志 ----
    log_file: str = field(default_factory=lambda: _env_str("LOG_FILE", "deskpal.log"))
    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO"))


# 模块级单例：业务代码统一 `from deskpal.config import settings` 使用。
# 测试时如需不同配置，直接构造 `Settings(db_path=":memory:")` 即可。
_load_dotenv()  # 先加载 .env，让密钥可被 Settings 读取
settings = Settings()
