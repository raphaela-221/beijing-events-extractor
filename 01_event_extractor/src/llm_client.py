"""Shared LLM client factory.

Defaults to Volcano Engine Ark (OpenAI-compatible endpoint) when ARK_API_KEY is
set, and falls back to generic OpenAI-compatible config (e.g. DeepSeek) when Ark
variables are not set.

call_llm() adds automatic runtime fallback: if the primary (Ark) call fails and
a DeepSeek-direct key (OPENAI_API_KEY) is configured, the call is retried against
api.deepseek.com so extraction keeps working when Ark is down/key-invalid.
"""
import logging
import os
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


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


def _get_fallback_client():
    """Return (DeepSeek-direct client, model) if fallback is configured, else None.

    Fallback is active only when:
    - primary is Ark (otherwise primary already uses OPENAI_* config, so there
      is no separate DeepSeek-direct path to fall back to); AND
    - OPENAI_API_KEY is set (a DeepSeek-direct key, sk-*, distinct from the
      Ark ark- key which does not work on api.deepseek.com).
    """
    if not _using_ark():
        return None
    deepseek_key = os.getenv("OPENAI_API_KEY")
    if not deepseek_key:
        return None

    import httpx

    bypass_proxy = os.getenv("OPENAI_BYPASS_PROXY", "1") == "1"
    http_client = httpx.Client(timeout=300.0, trust_env=not bypass_proxy)
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)
    client = OpenAI(base_url=base_url, api_key=deepseek_key, http_client=http_client)
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    return client, model


# Cumulative LLM usage tracker (provider -> {calls, prompt, completion, total}).
# Populated by call_llm; print_usage_summary() dumps it at end of run so the
# user can see which API handled the work and how many tokens were spent.
_USAGE = {
    "ark": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
    "deepseek": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
}


def _track_usage(provider: str, response) -> None:
    """Accumulate token usage from a chat completion response."""
    usage = getattr(response, "usage", None)
    if not usage:
        return
    bucket = _USAGE[provider]
    bucket["calls"] += 1
    bucket["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
    bucket["completion"] += getattr(usage, "completion_tokens", 0) or 0
    bucket["total"] += getattr(usage, "total_tokens", 0) or 0


def _log_call(provider_label: str, model: str, response) -> None:
    """Log a single LLM call's provider + token usage (visible in console)."""
    usage = getattr(response, "usage", None)
    if usage:
        logger.info(
            "[LLM] %s | model=%s | prompt=%d completion=%d total=%d tok",
            provider_label,
            model,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
            getattr(usage, "total_tokens", 0) or 0,
        )
    else:
        logger.info("[LLM] %s | model=%s | (usage 未返回)", provider_label, model)


def print_usage_summary() -> None:
    """Print cumulative LLM token usage to stdout (call at end of run)."""
    if not any(_USAGE[p]["calls"] for p in _USAGE):
        return
    print("\n📊 LLM 用量统计")
    total_calls = 0
    total_tok = 0
    for provider, label in (("ark", "Ark 主（火山引擎）"), ("deepseek", "DeepSeek 直连（兜底）")):
        u = _USAGE[provider]
        if not u["calls"]:
            continue
        print(
            f"  {label}：{u['calls']} 次调用 | "
            f"prompt {u['prompt']} + completion {u['completion']} = {u['total']} tok"
        )
        total_calls += u["calls"]
        total_tok += u["total"]
    print(f"  合计：{total_calls} 次调用 | {total_tok} tok")


def call_llm(
    messages,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_completion_tokens: Optional[int] = None,
    response_format: Optional[dict] = None,
    **extra,
):
    """Call the LLM with automatic DeepSeek-direct fallback.

    Primary: Ark (if ARK_API_KEY set) else OpenAI/DeepSeek.
    Fallback: if primary is Ark and OPENAI_API_KEY is set, retry on Ark failure
    with DeepSeek direct (api.deepseek.com). Returns the OpenAI ChatCompletion
    response. Raises the primary error if no fallback is configured; raises the
    fallback error if the fallback also fails.

    DeepSeek direct uses max_tokens (not max_completion_tokens); the wrapper
    converts automatically. Each call logs its provider + token usage and
    accumulates into the module-level tracker (see print_usage_summary).
    """
    primary_client = get_llm_client()
    primary_model = model or get_llm_model()

    call_kwargs = {}
    if temperature is not None:
        call_kwargs["temperature"] = temperature
    if max_completion_tokens is not None:
        call_kwargs["max_completion_tokens"] = max_completion_tokens
    if response_format is not None:
        call_kwargs["response_format"] = response_format
    call_kwargs.update({k: v for k, v in extra.items() if v is not None})

    try:
        response = primary_client.chat.completions.create(
            model=primary_model,
            messages=messages,
            **call_kwargs,
        )
        _track_usage("ark", response)
        _log_call("Ark 主", primary_model, response)
        return response
    except Exception as primary_err:
        fallback = _get_fallback_client()
        if fallback is None:
            raise
        fallback_client, fallback_model = fallback
        logger.warning(
            "Primary LLM (Ark) failed: %s. Falling back to DeepSeek direct "
            "(model=%s).",
            primary_err,
            fallback_model,
        )
        # DeepSeek direct uses max_tokens, not max_completion_tokens
        fb_kwargs = dict(call_kwargs)
        if "max_completion_tokens" in fb_kwargs:
            fb_kwargs["max_tokens"] = fb_kwargs.pop("max_completion_tokens")
        response = fallback_client.chat.completions.create(
            model=fallback_model,
            messages=messages,
            **fb_kwargs,
        )
        _track_usage("deepseek", response)
        _log_call("DeepSeek 直连(兜底)", fallback_model, response)
        return response
