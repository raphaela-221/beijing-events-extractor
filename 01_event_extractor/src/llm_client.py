"""Shared LLM client factory —— 多段兜底链。

调用链优先级（2026-09-15 用户裁决定档）：
  主       DeepSeek 直连（api.deepseek.com，OpenAI 协议）
  兜底 1   火山引擎 Ark Agent Plan（api/plan，Anthropic 协议）
  兜底 2   明略 mlamp 网关（llmgw-bz.mlamp.cn，OpenAI 协议）  ← 终极兜底
  兜底 3   Qwen 内网 POMP（pomp.ubrmbqa.com，OpenAI 协议）    ← 免费最后兜底

说明：
- 每跳失败（超时/限流/key 失效/网关断连/空返回）自动切下一跳，逐跳日志。
- Ark 是 Anthropic 兼容端点（api/plan），走 raw httpx + x-api-key；chat/completions 会 401。
- mlamp 是 OpenAI 兼容网关，Authorization: Bearer <token>。长 prompt 非流式约 60-66s
  断连，所以长请求默认 stream=true（攒够一次性吐出来）。
- Qwen 走项目内 vendored `vendor/pomp_minimal_call.py`（call_pomp_stream，流式防 504）。
  该端点免 key（内网），需 trust_env=False + verify=False。

call_llm() 返回 OpenAI ChatCompletion 形状的对象（choices[0].message.content /
usage.*），调用方不变。每个 provider 独立统计用量，print_usage_summary() 汇总。

Qwen 作为「日期抽取主力」的用法见 enrich_concert_dates.py（--provider qwen），
不走本文件的 call_llm 兜底链，而是直接调 call_qwen38()（该任务输入输出都极小、
格式规整，Qwen 免费内网可稳定胜任，且兜底链仍由 call_llm 提供）。
"""
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/plan"
DEFAULT_ARK_MODEL = "deepseek-v4-flash"
DEFAULT_OPENAI_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_OPENAI_MODEL = "deepseek-chat"
DEFAULT_MLAMP_BASE_URL = "https://llmgw-bz.mlamp.cn/v1/chat/completions"
DEFAULT_MLAMP_MODEL = "deepseek-v4.1-flash"

# Qwen POMP 内网（vendored，随包分发）：免 key，流式防 504
VENDOR_POMP = Path(__file__).resolve().parents[2] / "vendor" / "pomp_minimal_call.py"


def _primary_is_deepseek() -> bool:
    """Primary is DeepSeek direct when its key is configured.

    When OPENAI_API_KEY is set, DeepSeek direct is primary and the fallback chain
    (Ark -> mlamp -> Qwen) kicks in on failure. When only other keys are set,
    the first configured provider becomes primary.
    """
    return bool(os.getenv("OPENAI_API_KEY"))


def _ark_is_anthropic() -> bool:
    """Ark endpoint uses the Anthropic-compatible api/plan endpoint (Agent Plan)
    when ARK_BASE_URL contains '/api/plan'."""
    base = os.getenv("ARK_BASE_URL", DEFAULT_ARK_BASE_URL)
    return "/api/plan" in base


# ============================================================
# Provider: DeepSeek direct (OpenAI SDK)
# ============================================================

def _deepseek_base_url() -> str:
    return os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)


def _deepseek_api_key() -> Optional[str]:
    return os.getenv("OPENAI_API_KEY")


def get_llm_model() -> str:
    """Return the model name for the primary provider (DeepSeek direct)."""
    return os.getenv("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL


def _new_http_client(timeout: float = 300.0) -> httpx.Client:
    bypass_proxy = os.getenv("OPENAI_BYPASS_PROXY", "1") == "1"
    return httpx.Client(timeout=timeout, trust_env=not bypass_proxy)


def _openai_client(base_url: str, api_key: str, timeout: float = 300.0) -> OpenAI:
    return OpenAI(base_url=base_url, api_key=api_key, http_client=_new_http_client(timeout))


# ============================================================
# Usage tracking
# ============================================================

_USAGE = {
    "deepseek": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
    "ark": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
    "mlamp": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
    "qwen": {"calls": 0, "prompt": 0, "completion": 0, "total": 0},
}

_PROVIDER_LABELS = {
    "deepseek": "DeepSeek 主（直连）",
    "ark": "Ark 兜底",
    "mlamp": "mlamp 兜底",
    "qwen": "Qwen 兜底",
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


def _log_call(provider: str, model: str, response) -> None:
    usage = getattr(response, "usage", None)
    label = _PROVIDER_LABELS.get(provider, provider)
    if usage:
        logger.info(
            "[LLM] %s | model=%s | prompt=%d completion=%d total=%d tok",
            label, model,
            getattr(usage, "prompt_tokens", 0) or 0,
            getattr(usage, "completion_tokens", 0) or 0,
            getattr(usage, "total_tokens", 0) or 0,
        )
    else:
        logger.info("[LLM] %s | model=%s | (usage 未返回)", label, model)


def print_usage_summary() -> None:
    if not any(_USAGE[p]["calls"] for p in _USAGE):
        return
    print("\n📊 LLM 用量统计")
    total_calls = 0
    total_tok = 0
    for provider in ("deepseek", "ark", "mlamp", "qwen"):
        u = _USAGE[provider]
        if not u["calls"]:
            continue
        print(
            f"  {_PROVIDER_LABELS[provider]}：{u['calls']} 次调用 | "
            f"prompt {u['prompt']} + completion {u['completion']} = {u['total']} tok"
        )
        total_calls += u["calls"]
        total_tok += u["total"]
    print(f"  合计：{total_calls} 次调用 | {total_tok} tok")


# ============================================================
# Response wrapper (uniform OpenAI ChatCompletion shape)
# ============================================================

def _wrapped_response(text: str, model: str = "", in_tok: int = 0, out_tok: int = 0,
                      finish_reason: str = "stop") -> object:
    message = type("M", (), {"content": text, "role": "assistant"})()
    choice = type("C", (), {
        "message": message, "finish_reason": finish_reason, "index": 0,
    })()
    resp = type("R", (), {
        "choices": [choice],
        "usage": type("U", (), {
            "prompt_tokens": in_tok, "completion_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
        })(),
        "model": model,
    })()
    return resp


# ============================================================
# Provider: Ark Agent Plan (Anthropic-compatible, api/plan)
# ============================================================

def _call_ark(messages, model: str, *, max_tokens: int = 4096,
              temperature: Optional[float] = None,
              response_format: Optional[dict] = None):
    """火山 Ark Agent Plan（Anthropic 协议）。x-api-key + anthropic-version。"""
    key = os.getenv("ARK_API_KEY")
    if not key:
        raise RuntimeError("ARK_API_KEY 未配置")
    base = os.getenv("ARK_BASE_URL", DEFAULT_ARK_BASE_URL)

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
        "Authorization": f"Bearer {key}",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    url = base.rstrip("/") + "/v1/messages"

    resp = httpx.post(url, headers=headers, json=body, timeout=300.0)
    resp.raise_for_status()
    data = resp.json()
    text = "".join(
        b.get("text", "") for b in data.get("content", []) or [] if b.get("type") == "text"
    )
    usage = data.get("usage", {}) or {}
    in_tok = usage.get("input_tokens", 0) or 0
    out_tok = usage.get("output_tokens", 0) or 0
    return _wrapped_response(text, data.get("model", model), in_tok, out_tok,
                             data.get("stop_reason") or "stop")


# ============================================================
# Provider: mlamp gateway (OpenAI-compatible)
# ============================================================

def _call_mlamp(messages, model: str, *, max_tokens: int = 4096,
                temperature: Optional[float] = None,
                response_format: Optional[dict] = None):
    """明略 mlamp 网关（OpenAI 兼容）。Authorization: Bearer <token>。

    长 prompt 非流式约 60-66s 断连，默认 stream=true（网关攒够一次吐出，
    客户端逐行累加 delta.content）。response_format 该网关不支持，忽略。
    """
    key = os.getenv("MLAMP_API_KEY")
    if not key:
        raise RuntimeError("MLAMP_API_KEY 未配置")
    url = os.getenv("MLAMP_BASE_URL", DEFAULT_MLAMP_BASE_URL)

    system_parts = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
    chat_messages = [
        {"role": m["role"], "content": str(m.get("content", ""))}
        for m in messages if m.get("role") != "system"
    ]
    if system_parts:
        chat_messages.insert(0, {"role": "system", "content": "\n\n".join(system_parts)})

    body = {
        "model": model,
        "messages": chat_messages,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if temperature is not None:
        body["temperature"] = temperature

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    content_acc = []
    got_any_choice = False
    with httpx.stream("POST", url, headers=headers, json=body, timeout=300.0) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[len("data: "):]
            if payload.strip() == "[DONE]":
                continue
            import json as _json
            try:
                obj = _json.loads(payload)
            except Exception:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            got_any_choice = True
            delta = choices[0].get("delta", {}) or {}
            piece = delta.get("content")
            if piece:
                content_acc.append(piece)
    if not got_any_choice:
        raise RuntimeError("mlamp 流式返回始终没有 choices")
    if not content_acc:
        raise RuntimeError("mlamp 返回有 choices 但 delta.content 全空（思考吃满额度？）")
    return _wrapped_response("".join(content_acc), model)


# ============================================================
# Provider: Qwen POMP 内网（vendored，免 key，最后兜底）
# ============================================================

def _call_qwen_pomp(messages, model: str = "Qwen3.8-27B", *, max_tokens: int = 4096,
                    temperature: Optional[float] = None):
    """Qwen 内网 POMP（OpenAI 兼容，免 key）。走 vendored call_pomp_stream。

    仅用于兜底链（免费最后兜底）。日期抽取主力不经过这里，直接调 call_qwen38()。
    """
    if not VENDOR_POMP.exists():
        raise RuntimeError(f"Qwen POMP 调用器缺失：{VENDOR_POMP}")
    sys.path.insert(0, str(VENDOR_POMP.parent))
    import pomp_minimal_call as pomp

    system_parts = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
    user_parts = [str(m.get("content", "")) for m in messages if m.get("role") != "system"]
    system = "\n\n".join(system_parts) or "You are a helpful assistant."
    prompt = "\n\n".join(user_parts)

    result = pomp.call_pomp_stream(
        prompt=prompt,
        system_prompt=system,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature if temperature is not None else 0.0,
        enable_thinking=False,
        print_mode="none",
    )
    text = result.get("final_text") or result.get("raw_content") or ""
    if not text.strip():
        raise RuntimeError("Qwen POMP 返回空内容")
    return _wrapped_response(text, model)


# ============================================================
# call_llm: 主（DeepSeek）→ Ark → mlamp → Qwen 四段兜底链
# ============================================================

def _deepseek_uses_max_tokens() -> bool:
    return True  # api.deepseek.com 用 max_tokens


def _adapt_kwargs(kwargs: dict, use_max_tokens: bool) -> dict:
    """Convert max_completion_tokens <-> max_tokens."""
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
    """主 DeepSeek 直连 + Ark(Anthropic) → mlamp → Qwen(POMP) 四段兜底链。

    返回 OpenAI ChatCompletion 形状对象。每跳失败自动切下一跳并记日志。
    各 provider 用量累计到 _USAGE（见 print_usage_summary）。
    """
    primary_model = model or get_llm_model()
    max_tokens = max_completion_tokens or 4096

    errors = []

    # 跳 1：DeepSeek 直连（主）
    if _deepseek_api_key():
        try:
            client = _openai_client(_deepseek_base_url(), _deepseek_api_key())
            kwargs = {}
            if temperature is not None:
                kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
            kwargs.update({k: v for k, v in extra.items() if v is not None})
            resp = client.chat.completions.create(
                model=primary_model, messages=messages, **kwargs
            )
            _track_usage("deepseek", resp)
            _log_call("deepseek", primary_model, resp)
            return resp
        except Exception as e:
            errors.append(f"DeepSeek 直连: {type(e).__name__}: {e}")
            logger.warning("DeepSeek 主失败，切 Ark：%s", e)

    # 跳 2：Ark（Anthropic 协议）
    ark_model = os.getenv("ARK_MODEL", DEFAULT_ARK_MODEL)
    if os.getenv("ARK_API_KEY"):
        try:
            resp = _call_ark(
                messages, ark_model, max_tokens=max_tokens,
                temperature=temperature, response_format=response_format,
            )
            _track_usage("ark", resp)
            _log_call("ark", ark_model, resp)
            return resp
        except Exception as e:
            errors.append(f"Ark: {type(e).__name__}: {e}")
            logger.warning("Ark 失败，切 mlamp：%s", e)

    # 跳 3：mlamp（OpenAI 兼容，终极兜底）
    mlamp_model = os.getenv("MLAMP_MODEL", DEFAULT_MLAMP_MODEL)
    if os.getenv("MLAMP_API_KEY"):
        try:
            resp = _call_mlamp(
                messages, mlamp_model, max_tokens=max_tokens,
                temperature=temperature, response_format=response_format,
            )
            _track_usage("mlamp", resp)
            _log_call("mlamp", mlamp_model, resp)
            return resp
        except Exception as e:
            errors.append(f"mlamp: {type(e).__name__}: {e}")
            logger.warning("mlamp 失败，切 Qwen：%s", e)

    # 跳 4：Qwen POMP 内网（免费最后兜底）
    try:
        resp = _call_qwen_pomp(
            messages, model="Qwen3.8-27B", max_tokens=max_tokens,
            temperature=temperature,
        )
        _track_usage("qwen", resp)
        _log_call("qwen", "Qwen3.8-27B", resp)
        return resp
    except Exception as e:
        errors.append(f"Qwen POMP: {type(e).__name__}: {e}")
        logger.warning("Qwen POMP 失败：%s", e)

    raise RuntimeError(
        "LLM 兜底链全部不可用：\n  " + "\n  ".join(errors)
    )


# ============================================================
# Qwen 主力调用（日期抽取专用）——直接走 vendored POMP，不进兜底链
# ============================================================

def call_qwen38(prompt: str, *, system: str = "你是一个有帮助的助手。",
                max_tokens: int = 512, temperature: float = 0.0) -> str:
    """调 Qwen3.8-27B（POMP 内网，免 key）抽日期。失败抛异常，由调用方决定是否走
    兜底链（call_llm）。返回纯文本（已剥 thinking + markdown 围栏）。"""
    if not VENDOR_POMP.exists():
        raise RuntimeError(f"Qwen POMP 调用器缺失：{VENDOR_POMP}")
    sys.path.insert(0, str(VENDOR_POMP.parent))
    import pomp_minimal_call as pomp
    result = pomp.call_pomp_stream(
        prompt=prompt,
        system_prompt=system,
        model="Qwen3.8-27B",
        max_tokens=max_tokens,
        temperature=temperature,
        enable_thinking=False,
        print_mode="none",
    )
    text = result.get("final_text") or result.get("raw_content") or ""
    if not text.strip():
        raise RuntimeError("Qwen POMP 返回空内容")
    return text
