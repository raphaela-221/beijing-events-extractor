"""Shared LLM client factory.

Defaults to Volcano Engine Ark (OpenAI-compatible endpoint) when ARK_API_KEY is
set, and falls back to generic OpenAI-compatible config (e.g. DeepSeek) when Ark
variables are not set.
"""
import os
from typing import Optional

from openai import OpenAI


DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_ARK_MODEL = "deepseek-v4-flash"
DEFAULT_OPENAI_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_OPENAI_MODEL = "deepseek-v4-flash"


def _using_ark() -> bool:
    """Ark is active if the user set an Ark key or an Ark base URL."""
    return bool(os.getenv("ARK_API_KEY") or os.getenv("ARK_BASE_URL"))


def _base_url() -> str:
    if _using_ark():
        return os.getenv("ARK_BASE_URL", DEFAULT_ARK_BASE_URL)
    return os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)


def _api_key() -> Optional[str]:
    if _using_ark():
        return os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")
    return os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY")


def get_llm_model() -> str:
    """Return the model name / endpoint ID to use.

    For Ark, this is usually the endpoint ID (e.g. ep-xxxxxxxx); for DeepSeek
    it's the model name (e.g. deepseek-v4-flash).
    """
    if _using_ark():
        return os.getenv("ARK_MODEL") or os.getenv("OPENAI_MODEL", DEFAULT_ARK_MODEL)
    return os.getenv("OPENAI_MODEL") or os.getenv("ARK_MODEL", DEFAULT_OPENAI_MODEL)


def get_llm_client(timeout: float = 300.0) -> OpenAI:
    """Create an OpenAI-compatible client from environment variables."""
    api_key = _api_key()
    base_url = _base_url()

    if not api_key:
        raise ValueError(
            "API key not set. Please set ARK_API_KEY (recommended) or OPENAI_API_KEY."
        )

    import httpx

    bypass_proxy = os.getenv("OPENAI_BYPASS_PROXY", "1") == "1"
    http_client = httpx.Client(
        timeout=timeout,
        trust_env=not bypass_proxy,
    )

    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        http_client=http_client,
    )
