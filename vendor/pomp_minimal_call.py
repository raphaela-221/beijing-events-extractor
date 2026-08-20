#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal streaming caller for the internal POMP/Qwen endpoint."""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import urllib3


DEFAULT_URL = "https://pomp.ubrmbqa.com:9997/modelapi/v1/chat/completions"
DEFAULT_MODEL = "Qwen3.6-27B"


def build_payload(
    prompt: str,
    system_prompt: str,
    model: str,
    stream: bool = True,
    max_tokens: int = 8192,
    temperature: float = 0.7,
    top_p: float = 0.8,
    top_k: int = 20,
    repetition_penalty: float = 1.07,
    enable_thinking: Optional[bool] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "max_tokens": max_tokens,
        "repetition_penalty": repetition_penalty,
        "stream": stream,
    }
    if enable_thinking is not None:
        payload["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
    return payload


def iter_sse_payloads(response: requests.Response) -> Iterable[Tuple[str, Optional[str]]]:
    for line in response.iter_lines(decode_unicode=True):
        if not line:
            continue
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data:
            yield data, line


def strip_thinking_and_fences(text: str) -> str:
    """Return the final answer after Qwen thinking text and Markdown fences."""
    result = text.strip()
    if "</think>" in result:
        result = result.rsplit("</think>", 1)[1].strip()
    if result.startswith("```"):
        lines = result.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        result = "\n".join(lines).strip()
    return result


def call_pomp_stream(
    prompt: str,
    system_prompt: str = "你是一个有帮助的助手。",
    url: str = DEFAULT_URL,
    model: str = DEFAULT_MODEL,
    connect_timeout: float = 10.0,
    read_timeout: float = 600.0,
    verify_tls: bool = False,
    max_tokens: int = 8192,
    temperature: float = 0.7,
    top_p: float = 0.8,
    top_k: int = 20,
    repetition_penalty: float = 1.07,
    enable_thinking: Optional[bool] = None,
    print_mode: str = "answer",
) -> Dict[str, Any]:
    """Call POMP with stream=true and return raw and cleaned text.

    print_mode:
      - none: print no streamed text
      - raw: print all streamed content, including thinking
      - answer: print only chunks after </think> when possible
    """
    if not verify_tls:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    payload = build_payload(
        prompt=prompt,
        system_prompt=system_prompt,
        model=model,
        stream=True,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repetition_penalty=repetition_penalty,
        enable_thinking=enable_thinking,
    )
    headers = {"Content-Type": "application/json"}

    started = time.perf_counter()
    first_chunk_at: Optional[float] = None
    content_chunks = 0
    reasoning_chunks = 0
    finish_reason: Optional[str] = None
    content_parts: List[str] = []
    reasoning_parts: List[str] = []
    answer_printing = False

    with requests.post(
        url,
        json=payload,
        headers=headers,
        verify=verify_tls,
        stream=True,
        timeout=(connect_timeout, read_timeout),
    ) as response:
        response.raise_for_status()
        for data, _raw_line in iter_sse_payloads(response):
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = event.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            if choice.get("finish_reason"):
                finish_reason = choice.get("finish_reason")
            delta = choice.get("delta") or {}
            content = delta.get("content") or ""
            reasoning = delta.get("reasoning_content") or ""
            if (content or reasoning) and first_chunk_at is None:
                first_chunk_at = time.perf_counter()
            if reasoning:
                reasoning_chunks += 1
                reasoning_parts.append(reasoning)
                if print_mode == "raw":
                    print(reasoning, end="", flush=True)
            if content:
                content_chunks += 1
                content_parts.append(content)
                if print_mode == "raw":
                    print(content, end="", flush=True)
                elif print_mode == "answer":
                    if answer_printing:
                        print(content, end="", flush=True)
                    elif "</think>" in content:
                        answer_printing = True
                        print(content.rsplit("</think>", 1)[1], end="", flush=True)

    raw_content = "".join(content_parts)
    raw_reasoning = "".join(reasoning_parts)
    final_text = strip_thinking_and_fences(raw_content)
    duration = time.perf_counter() - started
    first_chunk_seconds = None if first_chunk_at is None else round(first_chunk_at - started, 3)
    return {
        "raw_content": raw_content,
        "raw_reasoning": raw_reasoning,
        "final_text": final_text,
        "metrics": {
            "duration_seconds": round(duration, 3),
            "first_chunk_seconds": first_chunk_seconds,
            "content_chunks": content_chunks,
            "reasoning_chunks": reasoning_chunks,
            "content_chars": len(raw_content),
            "reasoning_chars": len(raw_reasoning),
            "finish_reason": finish_reason,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "repetition_penalty": repetition_penalty,
            "enable_thinking": enable_thinking,
        },
    }


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_file:
        return Path(args.prompt_file).read_text(encoding="utf-8")
    if args.prompt:
        return args.prompt
    return sys.stdin.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal POMP/Qwen streaming API caller")
    parser.add_argument("--prompt", default=None, help="Prompt text. If omitted, stdin is used.")
    parser.add_argument("--prompt-file", default=None, help="UTF-8 text file containing the prompt.")
    parser.add_argument("--system", default="你是一个有帮助的助手。")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out", default=None, help="Optional UTF-8 output file for the cleaned final text.")
    parser.add_argument("--raw-out", default=None, help="Optional UTF-8 output file for raw streamed content.")
    parser.add_argument("--metrics-out", default=None, help="Optional JSON file for metrics.")
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--read-timeout", type=float, default=600.0)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.8)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--repetition-penalty", type=float, default=1.07)
    parser.add_argument("--enable-thinking", action="store_true", help="Explicitly pass enable_thinking=true.")
    parser.add_argument("--disable-thinking", action="store_true", help="Explicitly pass enable_thinking=false.")
    parser.add_argument("--json-mode", action="store_true", help="Use low-temperature JSON-oriented defaults and validate final text as JSON.")
    parser.add_argument("--print-mode", choices=["none", "raw", "answer"], default="answer")
    parser.add_argument("--verify-tls", action="store_true")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    prompt = read_prompt(args).strip()
    if not prompt:
        raise SystemExit("empty prompt")

    enable_thinking: Optional[bool]
    if args.enable_thinking and args.disable_thinking:
        raise SystemExit("choose only one of --enable-thinking or --disable-thinking")
    if args.enable_thinking:
        enable_thinking = True
    elif args.disable_thinking:
        enable_thinking = False
    else:
        enable_thinking = None

    temperature = 0.0 if args.json_mode else args.temperature
    top_p = 1.0 if args.json_mode else args.top_p
    max_tokens = min(args.max_tokens, 2048) if args.json_mode and args.max_tokens == 8192 else args.max_tokens

    result = call_pomp_stream(
        prompt=prompt,
        system_prompt=args.system,
        url=args.url,
        model=args.model,
        connect_timeout=args.connect_timeout,
        read_timeout=args.read_timeout,
        verify_tls=args.verify_tls,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
        top_k=args.top_k,
        repetition_penalty=args.repetition_penalty,
        enable_thinking=enable_thinking,
        print_mode=args.print_mode,
    )

    final_text = result["final_text"]
    if args.json_mode:
        try:
            json.loads(final_text)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"final text is not valid JSON: {exc}") from exc

    if args.out:
        Path(args.out).write_text(final_text, encoding="utf-8")
    if args.raw_out:
        Path(args.raw_out).write_text(result["raw_content"], encoding="utf-8")
    if args.metrics_out:
        Path(args.metrics_out).write_text(json.dumps(result["metrics"], ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        "\n\n[metrics] {}".format(json.dumps(result["metrics"], ensure_ascii=False)),
        file=sys.stderr,
    )
    if args.print_mode == "none":
        print(final_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
