"""LLM 工厂：创建 DeepSeek 模型实例，支持 flash/pro 切换、超时与重试。

成本控制：日常用 flash（默认，低成本），复杂重构时 use_pro=True 切换高精度模型。
模型名与 base_url 均从 settings 读取，便于切换网关/代理。
"""
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage


def create_llm(settings, use_pro: bool = False):
    """根据配置创建 DeepSeek chat 模型。

    use_pro=False 用 flash（省钱），True 用 pro（高精度）。
    """
    model = settings.llm_model_pro if use_pro else settings.llm_model_flash
    kwargs = dict(
        model=model,
        model_provider=settings.llm_provider,  # 统一接口：provider 由配置决定
        api_key=settings.api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return init_chat_model(**kwargs)


class _MockChatLLM:
    """无 API key 时的占位模型：跑通全链路、验证容错降级。"""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        return AIMessage(content="（占位模型）请配置 DEEPSEEK_API_KEY 以启用真实回复。")


def create_llm_or_mock(settings, use_pro: bool = False):
    """有 key 用真实模型；无 key 用占位模型。切换真实模型无需改调用方。"""
    if settings.api_key:
        return create_llm(settings, use_pro)
    return _MockChatLLM()

