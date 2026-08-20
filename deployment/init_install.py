"""首次安装初始化：选端口 + 写 config/service.json。Windows 上由 安装.cmd 调用。

读 config/service.json（build_release.py 预生成，含 version/port=0/python/chromium_revision），
若 port=0 则从 10000-29999 选空闲端口填入；port 已存在则保留（升级不覆盖）。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SJ = ROOT / "config" / "service.json"
PORT_MIN = 10000
PORT_MAX = 29999  # 不含


def _listening_ports() -> set[int]:
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
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
    ports: set[int] = set()
    if not base.exists():
        return ports
    for d in base.iterdir():
        sj = d / "config" / "service.json"
        if not sj.exists():
            continue
        try:
            p = json.loads(sj.read_text(encoding="utf-8")).get("port")
            if isinstance(p, int):
                ports.add(p)
        except Exception:
            continue
    return ports


def pick_port() -> int | None:
    used = _listening_ports() | _registered_ports()
    for p in range(PORT_MIN, PORT_MAX):
        if p not in used:
            return p
    return None


def main() -> int:
    if not SJ.exists():
        print(f"错误：{SJ} 不存在（包损坏）", file=sys.stderr)
        return 1
    try:
        data = json.loads(SJ.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"错误：service.json 解析失败: {e}", file=sys.stderr)
        return 1
    port = data.get("port")
    if port:
        print(f"端口已配置：{port}（保留，升级不覆盖）")
    else:
        port = pick_port()
        if not port:
            print(f"错误：{PORT_MIN}-{PORT_MAX} 无空闲端口", file=sys.stderr)
            return 1
        data["port"] = port
        SJ.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已选端口 {port}（写入 config/service.json）")
    print(f"\n浏览器访问: http://localhost:{port}")
    print(f"局域网访问: http://本机IP:{port}")
    print("默认账号 admin / operator，密码 change-me（首次启动后端自动创建，登录后请改）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
