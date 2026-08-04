"""Shared LLM client factory.

Primary: DeepSeek direct (api.deepseek.com) when OPENAI_API_KEY is set.
Fallback: Volcano Engine Ark when ARK_API_KEY is also set.

The Ark fallback supports BOTH endpoint types, auto-detected from ARK_BASE_URL:
  - api/plan  -> Anthropic-compatible (Agent Plan, e.g. ark-code-latest / Claude
                 models). Called via raw httpx with thinking disabled; response
                 is wrapped to look like an OpenAI ChatCompletion so call sites
                 stay unchanged. No `anthropic` package needed.
  - api/v3    -> OpenAI-compatible (regular Ark model inference via endpoint ID).

call_llm() adds automatic runtime fallback: if the primary call fails and the
other provider is configured, the call is retried against it. Each call logs
which provider handled it and the token usage; print_usage_summary() dumps the
cumulative totals at end of run.
"""
import logging
import os
from typing import Optional

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_ARK_MODEL = "ark-code-latest"
DEFAULT_OPENAI_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_OPENAI_MODEL = "deepseek-chat"


def _primary_is_deepseek() -> bool:
    """Primary is DeepSeek direct when its key is configured.

    When OPENAI_API_KEY is set, DeepSeek direct is primary and Ark (if
    configured) is the fallback. When only ARK_API_KEY is set, Ark is primary
    with no fallback.
    """
    return bool(os.getenv("OPENAI_API_KEY"))


def _ark_is_anthropic() -> bool:
    """Ark fallback uses the Anthropic-compatible api/plan endpoint (Agent Plan)
    when ARK_BASE_URL contains '/api/plan'. Otherwise it's OpenAI-compatible
    (api/v3, regular model inference)."""
    base = os.getenv("ARK_BASE_URL", DEFAULT_ARK_BASE_URL)
    return "/api/plan" in base


# ============================================================
# Primary client (OpenAI SDK: DeepSeek direct, or regular Ark api/v3)
# ============================================================

def _base_url() -> str:
    if _primary_is_deepseek():
        return os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)
    return os.getenv("ARK_BASE_URL", DEFAULT_ARK_BASE_URL)


def _api_key() -> Optional[str]:
    if _primary_is_deepseek():
        return os.getenv("OPENAI_API_KEY") or os.getenv("ARK_API_KEY")
    return os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY")


def get_llm_model() -> str:
    """Return the model name / endpoint ID to use for the primary provider."""
    if _primary_is_deepseek():
        return os.getenv("OPENAI_MODEL") or os.getenv("ARK_MODEL", DEFAULT_OPENAI_MODEL)
    return os.getenv("ARK_MODEL") or os.getenv("OPENAI_MODEL", DEFAULT_ARK_MODEL)


def get_llm_client(timeout: float = 300.0) -> OpenAI:
    """Create an OpenAI-compatible client for the primary provider."""
    api_key = _api_key()
    base_url = _base_url()

    if not api_key:
        raise ValueError(
            "API key not set. Please set OPENAI_API_KEY (DeepSeek direct, "
            "primary) or ARK_API_KEY (Ark, fallback)."
        )

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


# ============================================================
# Fallback config
# ============================================================

def _get_fallback_config():
    """Return fallback config dict, or None if not configured.

    Keys: provider_key ("ark"|"deepseek"), model, is_anthropic (bool),
    base_url, api_key.
    """
    if _primary_is_deepseek():
        # primary is DeepSeek; fallback is Ark
        ark_key = os.getenv("ARK_API_KEY")
        if not ark_key:
            return None
        return {
            "provider_key": "ark",
            "model": os.getenv("ARK_MODEL", DEFAULT_ARK_MODEL),
            "is_anthropic": _ark_is_anthropic(),
            "base_url": os.getenv("ARK_BASE_URL", DEFAULT_ARK_BASE_URL),
            "api_key": ark_key,
        }
    else:
        # primary is Ark; fallback is DeepSeek direct
        deepseek_key = os.getenv("OPENAI_API_KEY")
        if not deepseek_key:
            return None
        return {
            "provider_key": "deepseek",
            "model": os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            "is_anthropic": False,
            "base_url": os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL),
            "api_key": deepseek_key,
        }


def _build_openai_client(base_url: str, api_key: str, timeout: float = 300.0) -> OpenAI:
    bypass_proxy = os.getenv("OPENAI_BYPASS_PROXY", "1") == "1"
    http_client = httpx.Client(timeout=timeout, trust_env=not bypass_proxy)
    return OpenAI(base_url=base_url, api_key=api_key, http_client=http_client)


# ============================================================
# Anthropic-compatible call (Ark Agent Plan via api/plan)
# ============================================================

class _WrappedResponse:
    """Wraps an Anthropic Messages response to look like an OpenAI ChatCompletion
    so call sites (response.choices[0].message.content, response.usage.*) work
    unchanged."""

    def __init__(self, data: dict):
        text = "".join(
            b.get("text", "")
            for b in data.get("content", []) or []
            if b.get("type") == "text"
        )
        usage = data.get("usage", {}) or {}
        in_tok = usage.get("input_tokens", 0) or 0
        out_tok = usage.get("output_tokens", 0) or 0

        message = type("M", (), {"content": text, "role": "assistant"})()
        choice = type("C", (), {
            "message": message,
            "finish_reason": data.get("stop_reason") or "stop",
            "index": 0,
        })()
        self.choices = [choice]
        self.usage = type("U", (), {
            "prompt_tokens": in_tok,
            "completion_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
        })()
        self.model = data.get("model", "")


def _call_anthropic(base_url: str, api_key: str, model: str, messages, *,
                    max_tokens: int = 4096, temperature: Optional[float] = None,
                    response_format: Optional[dict] = None) -> _WrappedResponse:
    """Call an Anthropic-compatible endpoint (Volcano Ark Agent Plan).

    OpenAI messages -> Anthropic: system messages are pulled into the `system`
    param; the rest pass through as user/assistant turns. thinking is disabled
    to keep the fallback cheap and deterministic. JSON mode (response_format)
    is conveyed via a system instruction (Anthropic has no native json_object
    flag on this endpoint).
    """
    system_parts = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
    anthropic_messages = [
        {"role": m["role"], "content": str(m.get("content", ""))}
        for m in messages if m.get("role") != "system"
    ]

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": anthropic_messages,
        "thinking": {"type": "disabled"},
    }
    if system_parts:
        body["system"] = "\n\n".join(system_parts)
    if response_format and response_format.get("type") == "json_object":
        body["system"] = (body.get("system") or "") + (
            "\n\n输出必须是严格的合法 JSON，不要包含任何 JSON 之外的文字或 markdown 代码块。"
        )
    if temperature is not None:
        body["temperature"] = temperature

    headers = {
        "Authorization": f"Bearer {api_key}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    url = base_url.rstrip("/") + "/v1/messages"

    resp = httpx.post(url, headers=headers, json=body, timeout=300.0)
    resp.raise_for_status()
    return _WrappedResponse(resp.json())


# ============================================================
# Usage tracking
# ============================================================

_USAGE = {
    "deepseek": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
    "ark": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
}


def _track_usage(provider: str, response) -> None:
    usage = getattr(response, "usage", None)
    if not usage:
        return
    bucket = _USAGE[provider]
    bucket["calls"] += 1
    bucket["prompt"] += getattr(usage, "prompt_tokens", 0) or 0
    bucket["completion"] += getattr(usage, "completion_tokens", 0) or 0
    bucket["total"] += getattr(usage, "total_tokens", 0) or 0


def _log_call(provider_label: str, model: str, response) -> None:
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
    if not any(_USAGE[p]["calls"] for p in _USAGE):
        return
    print("\n📊 LLM 用量统计")
    total_calls = 0
    total_tok = 0
    for provider, label in (("deepseek", "DeepSeek 主（直连）"), ("ark", "Ark 兜底")):
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


# ============================================================
# call_llm: primary + automatic fallback
# ============================================================

def _adapt_kwargs(kwargs: dict, use_max_tokens: bool) -> dict:
    """Convert max_completion_tokens <-> max_tokens.

    DeepSeek direct and Anthropic (Agent Plan) both use max_tokens; regular Ark
    api/v3 uses max_completion_tokens.
    """
    kw = dict(kwargs)
    if use_max_tokens and "max_completion_tokens" in kw:
        kw["max_tokens"] = kw.pop("max_completion_tokens")
    return kw


def call_llm(
    messages,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_completion_tokens: Optional[int] = None,
    response_format: Optional[dict] = None,
    **extra,
):
    """Call the LLM with automatic fallback to the other provider.

    Primary: DeepSeek direct (if OPENAI_API_KEY set) else Ark.
    Fallback: the other provider if its key is configured. Ark fallback auto-
    detects Anthropic (api/plan, Agent Plan) vs OpenAI (api/v3) format.

    Each call logs its provider + token usage and accumulates into the
    module-level tracker (see print_usage_summary).
    """
    primary_client = get_llm_client()
    primary_model = model or get_llm_model()
    primary_is_deepseek = _primary_is_deepseek()

    base_kwargs = {}
    if temperature is not None:
        base_kwargs["temperature"] = temperature
    if max_completion_tokens is not None:
        base_kwargs["max_completion_tokens"] = max_completion_tokens
    if response_format is not None:
        base_kwargs["response_format"] = response_format
    base_kwargs.update({k: v for k, v in extra.items() if v is not None})

    primary_label = "DeepSeek 主（直连）" if primary_is_deepseek else "Ark 主"
    primary_provider_key = "deepseek" if primary_is_deepseek else "ark"
    # DeepSeek (api.deepseek.com) uses max_tokens; Ark api/v3 uses max_completion_tokens.
    primary_use_max_tokens = primary_is_deepseek

    try:
        response = primary_client.chat.completions.create(
            model=primary_model,
            messages=messages,
            **_adapt_kwargs(base_kwargs, use_max_tokens=primary_use_max_tokens),
        )
        _track_usage(primary_provider_key, response)
        _log_call(primary_label, primary_model, response)
        return response
    except Exception as primary_err:
        fallback = _get_fallback_config()
        if fallback is None:
            raise
        fb_label = "Ark 兜底" if primary_is_deepseek else "DeepSeek 直连(兜底)"
        fb_provider_key = fallback["provider_key"]
        fb_model = fallback["model"]
        logger.warning(
            "Primary LLM (%s) failed: %s. Falling back to %s (model=%s, %s).",
            "DeepSeek" if primary_is_deepseek else "Ark",
            primary_err,
            "Ark" if primary_is_deepseek else "DeepSeek",
            fb_model,
            "Anthropic" if fallback["is_anthropic"] else "OpenAI",
        )
        if fallback["is_anthropic"]:
            fb_kwargs = _adapt_kwargs(base_kwargs, use_max_tokens=True)
            fb_kwargs.setdefault("max_tokens", 4096)
            response = _call_anthropic(
                fallback["base_url"],
                fallback["api_key"],
                fb_model,
                messages,
                max_tokens=fb_kwargs.get("max_tokens", 4096),
                temperature=fb_kwargs.get("temperature"),
                response_format=fb_kwargs.get("response_format"),
            )
        else:
            fb_client = _build_openai_client(fallback["base_url"], fallback["api_key"])
            fb_kwargs = _adapt_kwargs(base_kwargs, use_max_tokens=(fb_provider_key == "deepseek"))
            response = fb_client.chat.completions.create(
                model=fb_model,
                messages=messages,
                **fb_kwargs,
            )
        _track_usage(fb_provider_key, response)
        _log_call(fb_label, fb_model, response)
        return response
