#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate data-grounded monthly take sentences via Ark (default) or Qwen.

Reads events_data.json, groups events by start month, and asks the configured
provider to analyze the events for that month and return ONE bilingual sentence
that captures the monthly city-pulse theme. The per-event analysis happens
inside the model; only the final zh/en sentence is persisted.

Usage:
    python3 generate_monthly_themes.py                    # generate for current year (Ark)
    python3 generate_monthly_themes.py --year 2026
    python3 generate_monthly_themes.py --month 2026-07    # single month
    python3 generate_monthly_themes.py --month 2026-07 --compare  # Ark + Qwen side-by-side
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

# 复用 01_event_extractor 的共享 LLM client（Ark 主 + DeepSeek 直连兜底），
# 避免 calendar 层重复维护 client 配置逻辑。
sys.path.insert(0, str(Path(__file__).parent.parent / "01_event_extractor"))
from src.llm_client import call_llm, print_usage_summary  # noqa: E402

ROOT = Path(__file__).parent
JSON_PATH = ROOT / "events_data.json"
COMMON_JS_PATH = ROOT / "common.js"
THEMES_JSON_PATH = ROOT / "monthly_themes.json"
COMPARISON_PATH = ROOT / "monthly_themes_comparison.json"
STATE_PATH = ROOT / "state" / "last_run.json"
POMP_SCRIPT = ROOT.parent / "vendor" / "pomp_minimal_call.py"

SYSTEM_PROMPT = "你是一位熟悉北京城市运行的分析助手。请严格按用户要求输出。"


def load_state():
    """Load delta state written by extract_demo_data.py."""
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict):
    """Persist delta state, including cached monthly themes."""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def write_comparison_md(comparison: dict, groups: dict):
    """Render a readable side-by-side Markdown table from comparison JSON."""
    meta = comparison.get("meta", {})
    last_run = meta.get("last_run", "")
    months = sorted(k for k in comparison if k != "meta")

    lines = [
        "# Ark vs Qwen 月度主题对比",
        "",
        f"> 生成时间：{last_run}",
        f"> 共对比 {len(months)} 个月份",
        "",
    ]
    for month in months:
        entries = comparison[month]
        count = len(groups.get(month, []))
        lines.append(f"## {month}（{count} 个事件）")
        lines.append("")
        lines.append("| 模型 | 中文 | 英文 |")
        lines.append("| --- | --- | --- |")
        for provider in ("ark", "qwen"):
            theme = entries.get(provider)
            if not theme:
                continue
            zh = str(theme.get("zh", "")).replace("|", "\\|")
            en = str(theme.get("en", "")).replace("|", "\\|")
            lines.append(f"| **{provider.upper()}** | {zh} | {en} |")
        lines.append("")

    md_path = ROOT / "monthly_themes_comparison.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote comparison markdown to {md_path}.", file=sys.stderr)


def load_events():
    records = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    # Keep only events with a parseable start date.
    valid = []
    for r in records:
        if r.get("start"):
            try:
                datetime.strptime(r["start"], "%Y-%m-%d")
                valid.append(r)
            except ValueError:
                pass
    return valid


def group_by_month(events):
    groups = defaultdict(list)
    for e in events:
        groups[e["start"][:7]].append(e)
    return groups


def build_prompt(month, events):
    lines = [
        f"请分析 {month} 当月共 {len(events)} 个事件，输出一句“本月观察”。",
        "",
        "要求：",
        "1. 先逐条理解事件标题、类型、关键词和描述（此分析过程不需要输出）。",
        "2. 仅根据事件实际提到的地点、性质或影响，总结当月北京城市脉搏主题。",
        "3. 对于外地中小学寒暑假、高校寒暑假及春秋假等集中假期事件：它们虽非北京本地活动，但会通过亲子游、研学游、探亲等方式影响北京地区的外地客流与消费热度，因此应视为“北京潜在客流/消费影响因子”，不要因地点在外地就忽略。如果事件日期与假期名称不一致（如 11 月发布暑假安排），以事件实际所指的放假时段为准判断其影响月份。",
        "4. 只有当事件明确提到环球度假区、主题公园、度假区或具体大型场馆时，才可以点出相关人流影响；否则不要编造地点或交通压力。",
        "5. 不要输出分析过程、解释或 Markdown 代码块。",
        "6. 最终只输出合法 JSON 对象：{\"zh\":\"中文句子\",\"en\":\"English sentence\"}。",
        "",
        "事件列表：",
    ]
    for i, e in enumerate(events, 1):
        desc = (e.get("description") or "").strip()
        # Truncate very long descriptions to keep the prompt within reason.
        if len(desc) > 300:
            desc = desc[:297] + "..."
        lines.append(
            f"{i}. [{e.get('start', '')}] {e.get('topic_zh', '')}｜{e.get('headline', '')}"
        )
        if e.get("keywords_zh"):
            lines.append(f"   关键词：{e['keywords_zh']}")
        if desc:
            lines.append(f"   描述：{desc}")
    return "\n".join(lines)


def call_qwen(prompt: str, retries: int = 1):
    if not POMP_SCRIPT.exists():
        raise FileNotFoundError(f"POMP script not found: {POMP_SCRIPT}")

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".txt", delete=False
    ) as f:
        f.write(prompt)
        prompt_file = f.name

    cmd = [
        sys.executable,
        str(POMP_SCRIPT),
        "--prompt-file",
        prompt_file,
        "--system",
        SYSTEM_PROMPT,
        "--enable-thinking",
        "--max-tokens",
        "8192",
        "--temperature",
        "0",
        "--print-mode",
        "none",
    ]

    last_error = None
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=600,
            )
            output = result.stdout.strip()
            if result.returncode != 0:
                raise RuntimeError(
                    f"POMP call failed (attempt {attempt + 1}): {result.stderr}"
                )
            data = json.loads(output)
            if "zh" not in data or "en" not in data:
                raise ValueError("Missing zh/en keys in output")
            return {"zh": str(data["zh"]).strip(), "en": str(data["en"]).strip()}
        except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries:
                print(f"  Retry {attempt + 1} for prompt...", file=sys.stderr)
    raise RuntimeError(f"Failed after {retries + 1} attempts: {last_error}")


def _extract_json_object(text: str) -> str:
    """Extract the first {...} object from a model response."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return text[start : end + 1]


def call_ark(prompt: str, retries: int = 1):
    """Call Ark (with DeepSeek-direct fallback) via the shared LLM client."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = call_llm(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_completion_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            data = json.loads(_extract_json_object(content))
            if "zh" not in data or "en" not in data:
                raise ValueError("Missing zh/en keys in output")
            return {"zh": str(data["zh"]).strip(), "en": str(data["en"]).strip()}
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                print(f"  Retry {attempt + 1} for Ark prompt...", file=sys.stderr)
    raise RuntimeError(f"Failed after {retries + 1} attempts: {last_error}")


def patch_common_js(themes: dict):
    """Replace the MONTHLY_THEMES object in common.js with generated themes."""
    text = COMMON_JS_PATH.read_text(encoding="utf-8")
    json_text = json.dumps(themes, ensure_ascii=False, indent=2)
    # We want a JS object literal; json.dumps output is valid JS for this data.
    new_declaration = f"const MONTHLY_THEMES = {json_text};"
    # Match the whole declaration, including multi-line nested objects.
    replaced, count = re.subn(
        r"const\s+MONTHLY_THEMES\s*=\s*\{[\s\S]*?\};",
        new_declaration,
        text,
        count=1,
    )
    if count == 0:
        raise RuntimeError("Could not find `const MONTHLY_THEMES = {...};` in common.js")
    COMMON_JS_PATH.write_text(replaced, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.now().year)
    parser.add_argument("--month", help="Single month in YYYY-MM format")
    parser.add_argument(
        "--min-events", type=int, default=5, help="Skip months with fewer events"
    )
    parser.add_argument(
        "--provider",
        choices=["ark", "qwen"],
        default="ark",
        help="Theme provider: ark (default) or qwen",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Also generate with the other provider and write side-by-side comparison",
    )
    args = parser.parse_args()

    events = load_events()
    groups = group_by_month(events)

    if args.month:
        target_months = [args.month]
    else:
        target_months = sorted(
            m for m in groups if m.startswith(str(args.year)) and len(groups[m]) >= args.min_events
        )

    if not target_months:
        print("No months match the criteria.", file=sys.stderr)
        return 1

    state = load_state()
    changed_months = set(state.get("changed_months", []))
    cached_themes = state.get("month_themes", {})

    # Start from the existing themes cache so previously generated themes are preserved.
    generated = {}
    if THEMES_JSON_PATH.exists():
        try:
            generated = json.loads(THEMES_JSON_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            generated = {}
    for month, theme in cached_themes.items():
        if month not in generated:
            generated[month] = theme

    # If there is no delta state yet, treat all target months as changed.
    if not state:
        changed_months = set(target_months)

    provider_func = call_ark if args.provider == "ark" else call_qwen
    other_func = call_qwen if args.provider == "ark" else call_ark
    other_name = "qwen" if args.provider == "ark" else "ark"
    provider_label = args.provider.upper()

    comparison = {}
    if args.compare:
        if COMPARISON_PATH.exists():
            try:
                comparison = json.loads(COMPARISON_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                comparison = {}
        comparison.setdefault("meta", {})["last_run"] = datetime.now().isoformat()

    failed_months = set()
    processed_months = set()
    skipped_count = 0
    for month in target_months:
        month_events = sorted(groups[month], key=lambda e: e["start"] or "")

        # Skip unchanged months unless the user explicitly asked for this month.
        if (
            not args.month
            and month not in changed_months
            and month in generated
        ):
            print(
                f"Skipping {month} ({len(month_events)} events) — no changes since last run.",
                file=sys.stderr,
            )
            skipped_count += 1
            continue

        processed_months.add(month)
        print(f"[{provider_label}] Generating theme for {month} ({len(month_events)} events)...", file=sys.stderr)
        prompt = build_prompt(month, month_events)
        try:
            theme = provider_func(prompt)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            failed_months.add(month)
            continue
        generated[month] = theme
        cached_themes[month] = theme
        print(f"  zh: {theme['zh']}", file=sys.stderr)
        print(f"  en: {theme['en']}", file=sys.stderr)

        if args.compare:
            try:
                print(f"[{other_name.upper()}] Generating comparison theme for {month}...", file=sys.stderr)
                other_theme = other_func(prompt)
                comparison[month] = {
                    args.provider: theme,
                    other_name: other_theme,
                }
                print(f"  zh: {other_theme['zh']}", file=sys.stderr)
                print(f"  en: {other_theme['en']}", file=sys.stderr)
            except Exception as exc:
                print(f"  ERROR ({other_name} comparison): {exc}", file=sys.stderr)

    THEMES_JSON_PATH.write_text(
        json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {THEMES_JSON_PATH} with {len(generated)} monthly themes.", file=sys.stderr)

    patch_common_js(generated)
    print(f"Patched {COMMON_JS_PATH}.", file=sys.stderr)

    if args.compare:
        COMPARISON_PATH.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Wrote side-by-side comparison to {COMPARISON_PATH}.", file=sys.stderr)
        write_comparison_md(comparison, groups)

    # Mark successfully processed months as no longer changed.
    processed = processed_months - failed_months
    state["changed_months"] = sorted((changed_months - processed) | failed_months)
    state["month_themes"] = cached_themes
    save_state(state)

    # 阶段成果块（操作台摘要解析器消费）
    print(f"📊 [Pipeline] themes 生成: {len(processed_months - failed_months)}")
    print(f"📊 [Pipeline] themes 跳过: {skipped_count}")
    print(f"📊 [Pipeline] themes 失败: {len(failed_months)}")

    # Print LLM usage (which API handled each call + token consumption)
    print_usage_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
