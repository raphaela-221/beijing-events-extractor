"""子进程执行器：启动 main.py，stdout 逐行落 jsonl，pub/sub 推 SSE，
取消时杀进程树（psutil，含 Playwright chromium 孤儿）。"""
from __future__ import annotations

import asyncio
import json
import os
import re
import traceback
from datetime import datetime
from typing import Any

import psutil

from .. import config
from ..lock import lock
from ..runs import store
from . import summary as summary_parser

# 显式 stage 标记（mock 用）：▶ stage:2
_EXPLICIT_STAGE = re.compile(r"▶ stage:(\d+)")

# 真实 scraper 关键词 -> 阶段索引（best-effort，按 stage 顺序取最高命中）
STAGE_KEYWORDS = [
    ["列表页", "正在采集演唱会信息"],
    ["详情页", "抽取成功", "抽取失败", "正在处理详情"],
    ["过滤", "剔除", "非北京", "场地小"],
    ["合并", "去重"],
    ["写入", "✅ 完成", "Excel 文件已保存", "已保存至"],
]


def infer_level(text: str) -> str:
    if any(k in text for k in ("❌", "ERROR", "Traceback", "错误：")):
        return "error"
    if any(k in text for k in ("⚠️", "WARN")):
        return "warn"
    if any(k in text for k in ("✓", "✅", "完成")):
        return "success"
    return "info"


def infer_stage(line: str, current: int, n_stages: int) -> int | None:
    m = _EXPLICIT_STAGE.search(line)
    if m:
        i = int(m.group(1))
        if 0 <= i < n_stages and i > current:
            return i
        return None
    best: int | None = None
    for idx, kws in enumerate(STAGE_KEYWORDS):
        if idx <= current or idx >= n_stages:
            continue
        if any(k in line for k in kws):
            best = idx
    return best


class RunManager:
    def __init__(self) -> None:
        self._procs: dict[str, dict] = {}  # run_id -> {"proc": Process, "stages": [...]}
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._cancelling: set[str] = set()

    # ---- pub/sub ----
    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs.setdefault(run_id, set()).add(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        s = self._subs.get(run_id)
        if s:
            s.discard(q)

    def _publish(self, run_id: str, event: str, data: dict) -> None:
        for q in list(self._subs.get(run_id, set())):
            q.put_nowait((event, data))

    def is_running(self, run_id: str) -> bool:
        info = self._procs.get(run_id)
        return info is not None and info["proc"].returncode is None

    def any_running(self) -> bool:
        return any(self.is_running(rid) for rid in list(self._procs))

    # ---- start ----
    async def start(
        self, run_id: str, argv: list[str], env: dict[str, str], stages: list[str],
        danger: str = "none",
    ) -> None:
        rd = config.RUNS_DIR / run_id
        jsonl_path = rd / "stdout.jsonl"
        log_path = rd / "stdout.log"
        store.update_run(run_id, status="running")
        self._publish(run_id, "status", {"status": "running"})
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(config.PROJECT_ROOT),
            env=env,
        )
        self._procs[run_id] = {"proc": proc, "stages": stages, "danger": danger}
        asyncio.create_task(self._pump(run_id, proc, jsonl_path, log_path, stages))

    async def _pump(
        self,
        run_id: str,
        proc: asyncio.subprocess.Process,
        jsonl_path,
        log_path,
        stages: list[str],
    ) -> None:
        seq = 0
        stage_index = -1
        sp = summary_parser.Parser()
        try:
            with open(jsonl_path, "a", encoding="utf-8") as fj, open(
                log_path, "a", encoding="utf-8"
            ) as fl:
                async for raw in proc.stdout:
                    line = raw.decode("utf-8", errors="replace").rstrip("\n")
                    seq += 1
                    ts = datetime.now().strftime("%H:%M:%S")
                    level = infer_level(line)
                    rec = {"seq": seq, "ts": ts, "level": level, "text": line}
                    fj.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fl.write(line + "\n")
                    fj.flush()
                    fl.flush()
                    store.update_run(run_id, log_lines=seq, log_bytes=jsonl_path.stat().st_size)
                    self._publish(run_id, "log", rec)
                    # 摘要
                    for evt, data in sp.feed(line):
                        self._apply_summary(run_id, evt, data)
                        self._publish(run_id, evt, data)
                    # 阶段
                    ns = infer_stage(line, stage_index, len(stages))
                    if ns is not None and ns != stage_index:
                        stage_index = ns
                        store.update_run(
                            run_id, stage_index=stage_index, current_stage=stages[stage_index]
                        )
                        self._publish(
                            run_id, "stage", {"stage_index": stage_index, "stage": stages[stage_index]}
                        )
            exit_code = await proc.wait()
            await self._finalize(run_id, exit_code)
        except Exception as e:
            traceback.print_exc()
            await self._finalize(run_id, -1, error=str(e))
        finally:
            self._procs.pop(run_id, None)

    def _apply_summary(self, run_id: str, event: str, data: dict) -> None:
        if event != "summary":
            return
        if "summary_json" in data:
            store.update_run(run_id, summary_json=json.dumps(data["summary_json"], ensure_ascii=False))
        if "llm_json" in data:
            store.update_run(run_id, llm_json=json.dumps(data["llm_json"], ensure_ascii=False))

    async def _finalize(self, run_id: str, exit_code: int, error: str | None = None) -> None:
        cancelling = run_id in self._cancelling
        self._cancelling.discard(run_id)
        info = self._procs.get(run_id, {})
        danger = info.get("danger", "none")
        run = store.get_run(run_id) or {}
        ended = datetime.now().isoformat(timespec="seconds")
        duration = store.parse_duration_ms(run.get("started_at", ended), ended)
        if cancelling:
            status = "cancelled"
            if danger in ("write_canonical", "destructive"):
                error_summary = "已停止，部分数据可能已写入，建议跑一次结构自检"
            else:
                error_summary = "已停止，本次未写入"
            error_kind = "cancelled"
        elif exit_code == 0:
            status, error_summary, error_kind = "success", None, None
        else:
            # 0 新数据特判：main.py 在 0 条新演唱会时走 "❌ 未能提取到任何事件" + exit 1，
            # 但采集流程已完整跑完（打印了汇总块、final=0），属正常空结果，不应显示为失败。
            is_no_data = False
            sumj = run.get("summary_json")
            if sumj:
                try:
                    s = json.loads(sumj)
                    concert = s.get("concert") if isinstance(s, dict) else None
                    if isinstance(concert, dict) and concert.get("final") == 0:
                        is_no_data = True
                except Exception:
                    pass
            if is_no_data:
                status = "success"
                error_summary = "本次无新数据采集（站点可达，列表已抓取，但无新演唱会）"
                error_kind = "no_new_data"
            else:
                status = "failed"
                error_summary = error or f"退出码 {exit_code}"
                error_kind = "unknown"
        store.update_run(
            run_id,
            status=status,
            exit_code=exit_code,
            ended_at=ended,
            duration_ms=duration,
            error_summary=error_summary,
            error_kind=error_kind,
        )
        self._publish(
            run_id,
            "status",
            {
                "status": status,
                "exit_code": exit_code,
                "error_summary": error_summary,
                "error_kind": error_kind,
                "ended_at": ended,
                "duration_ms": duration,
            },
        )
        operator = run.get("operator")
        if operator:
            lock.release(operator)

    # ---- cancel: 杀进程树 ----
    async def cancel(self, run_id: str) -> bool:
        info = self._procs.get(run_id)
        if not info:
            return False
        proc = info["proc"]
        if proc.returncode is not None:
            return False
        self._cancelling.add(run_id)
        try:
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
            for ch in children:
                try:
                    ch.terminate()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(children, timeout=3)
            for ch in parent.children(recursive=True):
                try:
                    ch.kill()
                except psutil.NoSuchProcess:
                    pass
            try:
                parent.kill()
            except psutil.NoSuchProcess:
                pass
        except psutil.NoSuchProcess:
            pass
        return True

    # ---- SSE 流 ----
    async def sse_stream(self, run_id: str, from_seq: int, request):
        def fmt(event: str, data: Any) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        # 1. 先订阅，避免回放与实时之间丢行
        q = self.subscribe(run_id)
        last_seq = from_seq
        try:
            # 2. 回放已落盘 seq > from_seq
            page = store.list_logs(run_id, from_seq, limit=100000)
            for rec in page["lines"]:
                yield fmt("log", rec)
                last_seq = rec["seq"]
            # 3. 从 DB 同步当前 meta（stage/summary/终态）
            r = store.get_run(run_id) or {}
            if r.get("stage_index") is not None:
                yield fmt(
                    "stage",
                    {"stage_index": r["stage_index"], "stage": r.get("current_stage")},
                )
            if r.get("summary_json"):
                yield fmt("summary", {"summary_json": json.loads(r["summary_json"])})
            if r.get("llm_json"):
                yield fmt("summary", {"llm_json": json.loads(r["llm_json"])})
            if r.get("status") in ("success", "failed", "cancelled"):
                yield fmt(
                    "status",
                    {
                        "status": r["status"],
                        "exit_code": r.get("exit_code"),
                        "error_summary": r.get("error_summary"),
                        "error_kind": r.get("error_kind"),
                    },
                )
                return
            # 4. 实时尾
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield fmt("heartbeat", {})
                    continue
                if event == "log":
                    if data.get("seq", 0) <= last_seq:
                        continue
                    last_seq = data["seq"]
                yield fmt(event, data)
                if event == "status" and data.get("status") in (
                    "success",
                    "failed",
                    "cancelled",
                ):
                    return
        finally:
            self.unsubscribe(run_id, q)


mgr = RunManager()
