"""构建 Windows 离线安装包（在 Mac/Linux 上跑）。

产物：release/<product>-Offline-Windows-x64-<ver>.zip + .sha256

流程：
  1. frontend npm run build
  2. 下载 Windows embeddable Python 3.12 -> python/，配 _pth 启用 site
  3. pip download win_amd64 cp312 wheels -> 解压进 python/Lib/site-packages/
  4. 下载 chromium-win64.zip (rev 1223) -> browsers/chromium-1223/
  5. 复制 app（backend + frontend/dist + 01_event_extractor + 02_calendar + canonical）
  6. 复制 deployment + scripts/audit + 写 config/service.json + MANIFEST.json
  7. zip + SHA256

用法：.venv/bin/python deployment/build_release.py [--version 1.0.0] [--skip-frontend]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PY = PROJECT_ROOT / ".venv" / "bin" / "python"

PRODUCT = "beijing-events-console"
VERSION = "1.0.0"
PYTHON_VERSION = "3.12.7"
CHROMIUM_REVISION = "1223"

EMBEDDABLE_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
CHROMIUM_URLS = [
    f"https://cdn.playwright.dev/builds/chromium/{CHROMIUM_REVISION}/chromium-win64.zip",
    f"https://playwright.azureedge.net/builds/chromium/{CHROMIUM_REVISION}/chromium-win64.zip",
]

IGNORE_DIRS = {"__pycache__", ".venv", "node_modules", ".pytest_cache", "dist", ".git"}
IGNORE_FILE_SUFFIXES = (".pyc", ".pyo")


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        while True:
            chunk = r.read(1024 * 64)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {dest.name} {done // 1024 // 1024}MB / {total // 1024 // 1024}MB ({pct}%)", end="", flush=True)
        print()


def try_download(urls: list[str], dest: Path) -> None:
    if dest.exists():
        log(f"已存在，跳过下载：{dest.name}")
        return
    last_err = None
    for url in urls:
        try:
            log(f"下载 {url}")
            download(url, dest)
            return
        except Exception as e:
            last_err = e
            log(f"失败：{e}")
    raise RuntimeError(f"全部下载源失败：{last_err}")


def unzip(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def patch_pth(python_dir: Path) -> None:
    """启用 site-packages：python312._pth 去掉 #import site 的 #。"""
    pth_files = list(python_dir.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError(f"找不到 ._pth 文件 in {python_dir}")
    for pth in pth_files:
        text = pth.read_text(encoding="utf-8")
        text = text.replace("#import site", "import site")
        pth.write_text(text, encoding="utf-8")
        log(f"已启用 site：{pth.name}")


def extract_wheels(wheels_dir: Path, site_packages: Path) -> None:
    """把每个 .whl 解压到 site-packages（wheel 是 zip，含 .py + win .pyd）。"""
    site_packages.mkdir(parents=True, exist_ok=True)
    wheels = sorted(wheels_dir.glob("*.whl"))
    log(f"解压 {len(wheels)} 个 wheel 到 site-packages")
    for whl in wheels:
        with zipfile.ZipFile(whl) as zf:
            zf.extractall(site_packages)


def merge_requirements() -> list[str]:
    reqs = []
    seen = set()
    # uvicorn[standard] 的 uvloop 仅 Unix；Mac 上跨平台 pip download 评估 marker 用运行平台，
    # 会认为要 uvloop 但无 win wheel -> ResolutionImpossible。拆成 uvicorn + standard 的
    # Windows 依赖（不含 uvloop，Windows 本就不用）。
    UVICORN_STANDARD_EXTRAS = ["httptools", "websockets", "python-dotenv", "watchfiles", "PyYAML"]
    for f in (PROJECT_ROOT / "requirements.txt", PROJECT_ROOT / "backend" / "requirements.txt"):
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("uvicorn[standard]"):
                ver = line[len("uvicorn[standard]"):]
                reqs.append(f"uvicorn{ver}")
                seen.add("uvicorn")
                for extra in UVICORN_STANDARD_EXTRAS:
                    if extra.lower() not in seen:
                        seen.add(extra.lower())
                        reqs.append(extra)
                continue
            name = line.split(">")[0].split("<")[0].split("=")[0].split("!")[0].split("[")[0].strip().lower()
            if name and name not in seen:
                seen.add(name)
                reqs.append(line)
    return reqs


def pip_download_wheels(wheels_dir: Path) -> None:
    wheels_dir.mkdir(parents=True, exist_ok=True)
    reqs = merge_requirements()
    log(f"依赖（去重后 {len(reqs)} 个）：{', '.join(reqs)}")
    # 写临时 requirements 文件
    tmp_req = wheels_dir.parent / "_merged_requirements.txt"
    tmp_req.write_text("\n".join(reqs) + "\n", encoding="utf-8")
    cmd = [
        str(VENV_PY), "-m", "pip", "download",
        "--platform", "win_amd64",
        "--python-version", "312",
        "--only-binary=:all:",
        "-r", str(tmp_req),
        "-d", str(wheels_dir),
    ]
    log(f"pip download win_amd64 cp312（慢，pandas 等大包）")
    res = subprocess.run(cmd, cwd=PROJECT_ROOT)
    tmp_req.unlink(missing_ok=True)
    if res.returncode != 0:
        raise RuntimeError(f"pip download 失败（某包可能无 win cp312 wheel，看上方报错）")


def copy_tree_filtered(src: Path, dst: Path) -> None:
    """复制目录，忽略 __pycache__/.venv/node_modules/dist 等。"""
    def ignore(dirpath, names):
        ign = [n for n in names if n in IGNORE_DIRS or any(n.endswith(s) for s in IGNORE_FILE_SUFFIXES)]
        return ign
    shutil.copytree(src, dst, ignore=ignore, dirs_exist_ok=True)


def build_frontend() -> None:
    log("frontend npm run build")
    res = subprocess.run(["npm", "run", "build"], cwd=PROJECT_ROOT / "frontend")
    if res.returncode != 0:
        raise RuntimeError("frontend build 失败")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default=VERSION)
    ap.add_argument("--skip-frontend", action="store_true")
    ap.add_argument("--with-initial-data", action="store_true",
                    help="携带本机 02_web_output/ + data/ 作为初始数据（历史日历成品+运行记录）")
    args = ap.parse_args()
    ver = args.version

    release_root = PROJECT_ROOT / "release"
    pkg_dir = release_root / f"{PRODUCT}-Offline-Windows-x64-{ver}"
    if pkg_dir.exists():
        shutil.rmtree(pkg_dir)
    pkg_dir.mkdir(parents=True)

    log(f"构建 {PRODUCT} v{ver} -> {pkg_dir}")

    # 1. frontend
    if not args.skip_frontend:
        build_frontend()
    else:
        log("跳过 frontend build（用现有 dist）")

    # 2. embeddable Python
    log("=== 便携 Python ===")
    py_zip = release_root / ".cache" / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    try_download([EMBEDDABLE_URL], py_zip)
    unzip(py_zip, pkg_dir / "python")
    patch_pth(pkg_dir / "python")

    # 3. wheels
    log("=== 离线 wheels ===")
    pip_download_wheels(pkg_dir / "wheels")
    extract_wheels(pkg_dir / "wheels", pkg_dir / "python" / "Lib" / "site-packages")
    # wheels 已解压进 site-packages，包内不留原件（省 ~60MB 传输体积）。
    # .dist-info 必须保留（playwright 等用 importlib.metadata 查版本）；.pyc 删掉，
    # Windows 首次运行自动重建。
    shutil.rmtree(pkg_dir / "wheels")
    n_pyc = 0
    for p in (pkg_dir / "python").rglob("*.pyc"):
        p.unlink()
        n_pyc += 1
    log(f"已删 wheels/ 原件 + {n_pyc} 个 .pyc（首次运行自动重建）")

    # 4. chromium：不内置。prss 网关拒绝非 playwright 客户端下载（curl/httpx/urllib 均 400
    #    GatewayExceptionResponse，要签名无法模拟）。改为首次运行时 start_server.py 调
    #    `playwright install chromium` 下载（Windows 出站网络，一次性 ~150MB，之后离线）。
    log("=== Chromium（首次运行由 playwright 下载，不内置）===")

    # 5. app
    log("=== 复制 app ===")
    app_dir = pkg_dir / "app"
    copy_tree_filtered(PROJECT_ROOT / "backend", app_dir / "backend")
    copy_tree_filtered(PROJECT_ROOT / "frontend" / "dist", app_dir / "frontend" / "dist")
    copy_tree_filtered(PROJECT_ROOT / "01_event_extractor", app_dir / "01_event_extractor")
    copy_tree_filtered(PROJECT_ROOT / "02_calendar", app_dir / "02_calendar")
    copy_tree_filtered(PROJECT_ROOT / "vendor", app_dir / "vendor")  # Qwen/POMP 调用脚本
    # canonical Excel
    canon_src = PROJECT_ROOT / "01_event_list_output" / "Events List.xlsx"
    canon_dst = app_dir / "01_event_list_output" / "Events List.xlsx"
    canon_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(canon_src, canon_dst)
    (app_dir / "01_raw_input").mkdir(parents=True, exist_ok=True)
    log("canonical + 01_raw_input 已就位")

    # 5.5 初始数据（可选）：历史日历成品 + 运行记录。skill 规则：仅明确要求时携带；
    #     升级到已有安装时，目标端已有 data/ 不得被初始数据覆盖（见使用说明升级步骤）。
    #     忽略 .db-shm（SQLite 共享内存索引，重启自动重建）；保留 .db-wal（未 checkpoint 的提交）。
    if args.with_initial_data:
        log("=== 初始数据（02_web_output + data/）===")

        def ignore_data(dirpath, names):
            return [n for n in names
                    if n in IGNORE_DIRS
                    or any(n.endswith(s) for s in IGNORE_FILE_SUFFIXES)
                    or n == ".DS_Store" or n.endswith(".db-shm")]

        shutil.copytree(PROJECT_ROOT / "02_web_output", app_dir / "02_web_output",
                        ignore=ignore_data, dirs_exist_ok=True)
        shutil.copytree(PROJECT_ROOT / "data", app_dir / "data",
                        ignore=ignore_data, dirs_exist_ok=True)
        log("已携带 02_web_output/ + data/（预览页与运行记录开箱即见）")
    else:
        log("未携带初始数据（预览页需先在服务器跑 Step2 生成日历）")

    # 6. deployment + scripts
    log("=== deployment + scripts ===")
    dep_src = PROJECT_ROOT / "deployment"
    dep_dst = pkg_dir / "deployment"
    dep_dst.mkdir(parents=True, exist_ok=True)
    for f in ("安装.cmd", "run.cmd", "init_install.py", "start_server.py", "使用说明.md"):
        shutil.copy2(dep_src / f, dep_dst / f)
    # 入口 cmd 同时放包根（用户解压直接看到）
    shutil.copy2(dep_src / "安装.cmd", pkg_dir / "安装.cmd")
    shutil.copy2(dep_src / "run.cmd", pkg_dir / "run.cmd")
    # 使用说明放包根一份，解压后第一眼可见（deployment/ 里另有原件）
    shutil.copy2(dep_src / "使用说明.md", pkg_dir / "使用说明.md")
    # 删 playwright 自带的辅助 .ps1（装系统 chrome/msedge 用，本项目不用；
    # IT 管控要求包内 .ps1 = 0，删后 playwright install chromium 不受影响）
    pw_bin = pkg_dir / "python" / "Lib" / "site-packages" / "playwright" / "driver" / "package" / "bin"
    n_ps1 = 0
    if pw_bin.exists():
        for ps1 in pw_bin.glob("*.ps1"):
            ps1.unlink()
            n_ps1 += 1
    log(f"已删 playwright 辅助 .ps1 {n_ps1} 个")
    scripts_dst = pkg_dir / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / "skills" / "package-windows-lan-app" / "scripts" / "audit_windows_ports.py",
        scripts_dst / "audit_windows_ports.py",
    )

    # 7. config/service.json + MANIFEST
    log("=== 配置 + 清单 ===")
    (pkg_dir / "config").mkdir(parents=True, exist_ok=True)
    service = {
        "product": PRODUCT,
        "version": ver,
        "port": 0,  # 安装时 init_install.py 选
        "python": PYTHON_VERSION,
        "chromium_revision": int(CHROMIUM_REVISION),
    }
    (pkg_dir / "config" / "service.json").write_text(
        json.dumps(service, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "product": PRODUCT,
        "version": ver,
        "runtime": f"Python {PYTHON_VERSION} (embeddable, win_amd64)",
        "chromium_revision": CHROMIUM_REVISION,
        "default_port_range": "10000-29999",
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "entry": "安装.cmd",
        "ps1_count": 0,
    }
    (pkg_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 8. zip + SHA256
    log("=== 打包 zip ===")
    zip_path = release_root / f"{pkg_dir.name}.zip"
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", root_dir=release_root, base_dir=pkg_dir.name)
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (zip_path.with_suffix(".sha256")).write_text(f"{sha}  {zip_path.name}\n", encoding="utf-8")
    log(f"完成：{zip_path}")
    log(f"SHA256：{sha}")
    log(f"大小：{zip_path.stat().st_size // 1024 // 1024} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
