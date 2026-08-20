---
name: package-windows-lan-app
description: 把 Python 后端 + 前端 build 项目打包成 Windows 离线一键安装包（便携 Python + 离线 wheels + 内置 Chromium + 安装.cmd），免管理员/免预装/免联网部署到 Windows 服务器
---

# package-windows-lan-app

把现有项目（Python 后端 + Vite/前端 build 产物）打包成 Windows **离线一键安装包**。目标服务器无需管理员权限、无需预装 Python/Node/Nginx、不改系统 PATH/防火墙/注册表。

## 硬约束（必须遵守）
- 入口用 `.cmd`，**严禁 `.ps1`**（IT 管控要求，验收时 `.ps1` 数量必须为 0）。
- per-user 安装到 `%LOCALAPPDATA%\Programs\<product>`，**免管理员**。
- 不改系统 PATH / 防火墙 / 注册表；**不注册系统服务**（启动项放当前用户启动文件夹，不是 NSSM/服务）。
- 端口从 **10000–29999** 选空闲（`scripts/audit_windows_ports.py`），不用 1–1023、不用 49152–65535 动态段；端口写 `config/service.json`，不在多处硬编码。
- 数据与程序分离：`data/` 目录升级**默认保留**；只有明确要求才携带初始数据，且不覆盖已有。
- **不生成 `.exe`**（IT 管控）。

## 打包机制（build_release.py，在 Mac/Linux 上跑）

1. **前端 build**：`npm run build` 生成 `frontend/dist/`。
2. **便携 Python**：下载 `python-3.12.x-embed-amd64.zip`（python.org ftp）-> 解压到 `python/` -> 编辑 `python312._pth` 去掉 `#import site` 的 `#`（启用 site-packages，否则依赖不生效）。
3. **离线 wheels**：`pip download --platform win_amd64 --python-version 312 --only-binary=:all: -r requirements.txt -d wheels/`，再用 `zipfile` 把每个 wheel 解压到 `python/Lib/site-packages/`。
   - **wheel 是 zip**，含 `.py` + win `.pyd` + 数据文件，解压即用，**不用跑 pip install**（embeddable Python 默认无 pip，解压法绕过 bootstrap）。
   - 不生成 `.dist-info/RECORD`，不影响运行（`pip list` 不显示，无妨，因为不跑 pip）。
4. **Chromium（首次运行下载，不内置）**：playwright 的浏览器不在 pip 里，且 prss 下载网关拒绝非 playwright 客户端（curl/urllib/httpx 均 400 GatewayExceptionResponse，要签名无法模拟）。改为 `start_server.py` 首次运行调 `playwright install chromium` 下载到 `browsers/`（Windows 出站网络，~150MB，之后离线）。`PLAYWRIGHT_BROWSERS_PATH` 指向 `browsers/`。
5. **复制 app**：`backend/` + `frontend/dist/` + pipeline 脚本 + canonical 数据 -> `app/`。
6. **deployment/**：`安装.cmd` + `run.cmd` + `service.json.template` + `MANIFEST.json` + `使用说明.md`。
7. **打包**：zip 成 `release/<product>-Offline-Windows-x64-<ver>.zip` + 算 SHA256 写 `.sha256`。

## 安装.cmd 逻辑（Windows 上首次安装跑）
- 解压/复制包内容到 `%LOCALAPPDATA%\Programs\<product>`。
- 选端口：调 `audit_windows_ports.py`（或内置逻辑）从 10000-29999 选空闲 -> 写 `config/service.json`（显示前后值）。
- 首次 seed `config/users.json`（admin/operator 默认密码，提示改）。
- 创建当前用户启动项 `beijing-events-console.cmd`（不注册服务）。
- **不跑 pip**（依赖已在 site-packages）。

## run.cmd 逻辑
- 设 `PLAYWRIGHT_BROWSERS_PATH=<root>\browsers`。
- 设 `CONSOLE_PORT` from `config/service.json`。
- `cd app` + `..\python\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port %CONSOLE_PORT%`。

## 端口审计（scripts/audit_windows_ports.py）
查实时 `netstat` 监听 + 扫 `%LOCALAPPDATA%\Programs\*/config/service.json` 已登记端口，从 10000-29999 选空闲。**不结束占用进程**；显式指定端口冲突则报 PID + 中文提示后失败，不静默换号。升级保留已选端口。

## 验证清单（§9）
- [ ] 打包前本地跑通全流程（编译/测试/`git diff --check`），失败不生成伪成功包。
- [ ] ZIP 校验 SHA256；解压确认入口/便携 Python/wheels/browsers/app/配置模板/清单完整，且 `.ps1` 数量为 0。
- [ ] `python/Lib/site-packages/` 抽查关键包（fastapi/uvicorn/openpyxl/pandas/playwright/bcrypt/psutil/pydantic_core）。
- [ ] 安装到 `%LOCALAPPDATA%\Programs\<product>-PackageTest-<ver>`，验证复制/配置渲染/端口保存/升级数据保留。
- [ ] 健康检查 + 浏览器验证管理入口、局域网入口、主要页面。
- [ ] 停测试服务时核对安装根目录和 PID；只删经解析确认的测试目录，不用通配符。
- [ ] 最终 ZIP + SHA256 复制到交付目录；只有用户要求刷新才移除旧包。

## 关联
- 《Web化评估与计划.md》§4（架构）+ §9（验证清单）- 本 skill 的来源。
- 单端口 MVP：FastAPI 绑 `0.0.0.0:<port>`。若要 API 不暴露局域网，引便携 Nginx 两端口模式（v2）。
