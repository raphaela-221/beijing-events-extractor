"""Windows 端口审计：为 LAN 应用选未占用端口。

查实时监听端口 + 扫 %LOCALAPPDATA%\\Programs\\*/config/service.json 已登记端口，
从 10000-29999 选空闲端口。不结束占用进程；显式指定端口冲突则报错退出。

用法：
  python audit_windows_ports.py                 # 自动选空闲端口，打印到 stdout
  python audit_windows_ports.py --prefer 12345  # 优先用指定端口，被占则报错
  python audit_windows_ports.py --json          # 输出 JSON（含已用端口列表）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PORT_MIN = 10000
PORT_MAX = 29999  # 不含


def _listening_ports() -> set[int]:
    """当前监听（LISTEN）的端口集合。"""
    try:
        import psutil
    except ImportError:
        return set()
    ports: set[int] = set()
    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == "LISTEN" and c.laddr:
                ports.add(c.laddr.port)
    except Exception:
        pass
    return ports


def _registered_ports() -> set[int]:
    """扫 %LOCALAPPDATA%\\Programs\\*/config/service.json 已登记端口。"""
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
    ports: set[int] = set()
    if not base.exists():
        return ports
    for d in base.iterdir():
        sj = d / "config" / "service.json"
        if not sj.exists():
            continue
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
            p = data.get("port")
            if isinstance(p, int):
                ports.add(p)
        except Exception:
            continue
    return ports


def used_ports() -> set[int]:
    return _listening_ports() | _registered_ports()


def pick_port(prefer: int | None = None) -> int | None:
    used = used_ports()
    if prefer is not None:
        if not (PORT_MIN <= prefer < PORT_MAX):
            return None
        if prefer in used:
            return None
        return prefer
    for p in range(PORT_MIN, PORT_MAX):
        if p not in used:
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="为 LAN 应用选未占用端口 (10000-29999)")
    ap.add_argument("--prefer", type=int, default=None, help="优先用指定端口，被占则报错")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    used = used_ports()
    port = pick_port(args.prefer)

    if args.json:
        print(json.dumps({"port": port, "used": sorted(used), "range": [PORT_MIN, PORT_MAX]}, ensure_ascii=False))
        return 0 if port else 1

    if port:
        print(port)
        print(f"# 端口 {port} 空闲（监听+已登记均未占用）", file=sys.stderr)
        return 0

    if args.prefer is not None:
        print(f"错误：端口 {args.prefer} 被占用或不在 {PORT_MIN}-{PORT_MAX} 范围", file=sys.stderr)
    else:
        print(f"错误：{PORT_MIN}-{PORT_MAX} 范围内无空闲端口", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
