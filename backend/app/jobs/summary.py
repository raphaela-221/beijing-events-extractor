"""摘要解析器：从 stdout 逐行解析 concert 采集回显块与 LLM 用量块（指南 §3.4）。

best-effort：解析失败静默跳过，不让运行记录挂掉。块在脚本末尾打印，
故摘要通常在运行接近结束时才填充（scraper 不打印逐条进度，无法实时滚动）。"""
from __future__ import annotations

import re
from typing import Any

_RE_LIST = re.compile(r"列表页分段：(\d+) 段（成功 (\d+) / 失败 (\d+)） \| 列表条目 (\d+)")
_RE_DETAIL = re.compile(r"详情页：(\d+) 条（成功 (\d+) / 失败 (\d+) / 无表格 (\d+)）")
_RE_FILT = re.compile(r"过滤：关键词 (\d+) / 已采集 (\d+) / 非北京 (\d+) / 场地小 (\d+)")
_RE_FINAL = re.compile(r"最终：(\d+) 条演唱会")
_RE_PROVIDER = re.compile(
    r"(.+?)：(\d+) 次调用 \| prompt (\d+) \+ completion (\d+) = (\d+) tok"
)
_RE_TOTAL = re.compile(r"合计：(\d+) 次调用 \| (\d+) tok")

_CONCERT_ANCHOR = "🎤 [Concert] 采集回显"
_LLM_ANCHOR = "📊 LLM 用量统计"
_PIPELINE_RE = re.compile(r"📊 \[Pipeline\] (\w+) (\w+): (.+)")


class Parser:
    def __init__(self) -> None:
        self.mode: str | None = None
        self.concert: dict[str, Any] = {}
        self.llm: dict[str, Any] = {"providers": [], "total": None}
        self.pipeline: dict[str, dict[str, Any]] = {}

    def feed(self, line: str) -> list[tuple[str, dict]]:
        """返回 [(event, data), ...]。event 为 'summary' 时 data 含 summary_json 或 llm_json。"""
        s = line.strip()
        events: list[tuple[str, dict]] = []
        if _CONCERT_ANCHOR in s:
            self.mode = "concert"
            self.concert = {}
            return events
        if _LLM_ANCHOR in s:
            self.mode = "llm"
            self.llm = {"providers": [], "total": None}
            return events
        if self.mode == "concert":
            for rx, keys in (
                (_RE_LIST, ("list_total", "list_ok", "list_failed", "list_items")),
                (_RE_DETAIL, ("detail_total", "detail_ok", "detail_failed", "detail_no_table")),
                (_RE_FILT, ("filt_keyword", "filt_dup", "filt_non_bj", "filt_venue")),
            ):
                m = rx.search(s)
                if m:
                    self.concert.update(zip(keys, (int(x) for x in m.groups())))
                    return events
            m = _RE_FINAL.search(s)
            if m:
                self.concert["final"] = int(m.group(1))
                events.append(("summary", {"summary_json": {"concert": self.concert}}))
                self.mode = None
                return events
        if self.mode == "llm":
            m = _RE_PROVIDER.search(s)
            if m:
                self.llm["providers"].append(
                    {
                        "label": m.group(1).strip(),
                        "calls": int(m.group(2)),
                        "prompt": int(m.group(3)),
                        "completion": int(m.group(4)),
                        "total": int(m.group(5)),
                    }
                )
                return events
            m = _RE_TOTAL.search(s)
            if m:
                self.llm["total"] = {"calls": int(m.group(1)), "tokens": int(m.group(2))}
                events.append(("summary", {"llm_json": self.llm}))
                self.mode = None
                return events
        # Pipeline 阶段成果块（每行独立：stage key: value，无锚点状态机）
        m = _PIPELINE_RE.search(s)
        if m:
            stage, key, raw = m.group(1), m.group(2), m.group(3).strip()
            try:
                val: Any = int(raw)
            except ValueError:
                val = raw
            self.pipeline.setdefault(stage, {})[key] = val
            events.append(("summary", {"summary_json": {"pipeline": dict(self.pipeline)}}))
        return events
