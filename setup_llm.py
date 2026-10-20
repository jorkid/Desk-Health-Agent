"""按 .env 里的 LLM_PROVIDER 自动安装对应依赖包（只装你选中的那个厂商）。

用法：python setup_llm.py

读 .env 的 LLM_PROVIDER，映射到对应的 langchain-<provider> 包；
已安装则跳过，未安装才 pip install，绝不装多余厂商。
"""
import importlib.util
import subprocess
import sys

from deskpal.config import settings

# 提供商 → 依赖包名（与 README「更换模型」表一致）
PROVIDER_PACKAGES = {
    "deepseek": "langchain-deepseek",      # 已在 requirements.txt，一般无需本脚本
    "openai": "langchain-openai",          # GPT / 豆包等 OpenAI 兼容端点
    "google_genai": "langchain-google-genai",
    "anthropic": "langchain-anthropic",
}


def _import_name(package: str) -> str:
    # 依赖包名用连字符，导入名用下划线：langchain-google-genai → langchain_google_genai
    return package.replace("-", "_")


def main() -> int:
    provider = settings.llm_provider
    package = PROVIDER_PACKAGES.get(provider)
    if package is None:
        print(f"[setup_llm] 未知提供商「{provider}」，请手动安装对应的 langchain-<provider> 包")
        return 1

    if importlib.util.find_spec(_import_name(package)) is not None:
        print(f"[setup_llm] {package} 已安装，无需操作")
        return 0

    print(f"[setup_llm] 提供商 {provider} → 安装 {package} ...")
    return subprocess.call([sys.executable, "-m", "pip", "install", package])


if __name__ == "__main__":
    sys.exit(main())
