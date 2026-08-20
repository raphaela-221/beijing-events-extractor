# 北京大事件整理系统 · Web 化评估与计划

> 目标：把现在「同事在自己电脑双击 `run.bat`」的桌面流程，改造成部署在公司 Windows 服务器、浏览器访问的内部操作台。
>
> 决策已拍板：①全流程操作台 ②核对用下载/上传往返（v1）③一次一人（v1）④Windows 服务器。
>
> 部署走 `package-windows-lan-app` skill 的成熟模式；3 个日历 HTML **已在服务器托管对外分享**，操作台只推送更新、不重复托管。

---

## 1. 现状速览

| 环节 | 现状 | 关键依赖 |
|---|---|---|
| Step 1 抽取 | `run.bat` -> `main.py`，读 `01_raw_input/` + 演唱会采集 -> LLM 抽取 -> 增量合并 Excel | DeepSeek 主 + Ark 兜底、Playwright Chromium（政府站 SM4） |
| 人工核对 | 桌面 Excel 改 canonical `Events List.xlsx` | canonical 含 Table/sharedStrings/数据验证，**禁 openpyxl save** |
| Step 2 生成 | `run_pipeline.py`：extract -> themes（Ark 增量）-> calendar -> package | canonical 唯一源；`state/last_run.json` 增量签名 |
| 发布 | **3 个日历 HTML 由自有项目管理平台托管对外分享**（zip 上传到平台项目） | 项目管理平台（上传方式待确认，见 4.4） |

Git 仓库：`github.com/raphaela-221/beijing-events-extractor`（私有，push 走 VPN 代理，运行时不依赖）。

---

## 2. 目标工作流

```
浏览器打开内部网址
 -> 上传原始文件 + 配置采集选项
 -> Step 1 后台跑（LLM + 演唱会采集），实时日志
 -> 下载 canonical Excel，桌面改，上传回传，校验 + 差异确认
 -> Step 2 后台跑（extract + themes + package），实时日志
 -> 预览 + 一键推送更新到已上线日历（URL 不变）+ 复制分享链接
```

---

## 3. 工作模块拆解

| 模块 | 内容 | 大小 | MVP |
|---|---|---|---|
| 后端 API | FastAPI 包 `main.py:process_files` + `run_pipeline` 各子命令为接口；登录 | 中 | 是 |
| 异步任务 + 实时日志 | 后台任务 + SSE 推日志 + 阶段进度；替代 bat 终端输出 | 中大 | 是 |
| 文件上传 + 状态管理 | 多文件上传；canonical + 两个 state 文件落 `data/` + 备份 | 中 | 是 |
| 编辑锁 | 单用户锁，占用提示与释放 | 小 | 是 |
| 核对往返（下载/上传） | 下载 canonical、上传校验（`verify_canonical`）、差异摘要、二次确认覆盖 | 中 | 是 |
| 日历更新推送 | 内置预览托管（StaticFiles）+ zip 上传到项目管理平台；URL 不变 | 中 | 是 |
| 打包与部署 | 用 `package-windows-lan-app` skill 生成离线安装包（便携 Python + 内置 Chromium + `安装.cmd`） | 中 | 是 |
| 前端操作台 | 见《Web前端设计需求.md》 | 中大 | 是 |
| 网页内编辑器（v2） | 在线表格编辑 canonical，走 XML 写法避开 openpyxl | 大 | 否 |
| 多用户并发（v2） | 排队、细粒度锁、冲突处理 | 大 | 否 |

---

## 4. 推荐架构（Windows 服务器，基于 `package-windows-lan-app` skill）

部署走 skill 的成熟模式：**离线一键安装包，目标服务器无需管理员权限、无需预装 Python/Node/Nginx、不改系统 PATH / 防火墙 / 注册表**。这推翻了上一版「NSSM 装系统服务 + 服务器装 Python/Chromium」的设想，以 skill 为准。

### 4.1 打包与安装机制
- 在本项目内增量加 `deployment/` 目录（skill 要求「在现有项目上增量加 deployment/installer，不重建项目」）。
- 用 skill 生成 `release/beijing-events-console-Offline-Windows-x64-<version>.zip`，入口 `安装.cmd`，**不含 `.ps1`**；附 SHA256 + UTF-8 清单（产品/版本/运行时/默认端口/构建时间）。
- 安装根目录 `%LOCALAPPDATA%\Programs\beijing-events-console`（per-user，免管理员）。
- **内置便携 Python + 全部依赖**（fastapi/uvicorn/openpyxl/pandas/openai/httpx/playwright/bs4 等）。
- **内置 Chromium**（打包最需注意的点）：Playwright 的浏览器不在 `pip install` 里，要把 Chromium 二进制打进包，运行时 `PLAYWRIGHT_BROWSERS_PATH` 指向安装目录下浏览器路径（约 +150MB，但保证免联网免管理员跑演唱会采集）。
- 登录自启：当前用户启动项 `beijing-events-console.cmd`（**不是系统服务**，不注册服务）。
- 数据与程序分离：`data/` 目录放 canonical Excel + 两个 state 文件 + 上传文件 + 日志，**升级默认保留**；只有明确要求才携带初始数据，且不覆盖已有数据。

### 4.2 端口规划（多项目共存）
- 日历读者端由项目管理平台托管（不一定在本 Windows 服务器）；本服务器上若还有其他 skill 打包的项目，端口审计避免冲突。
- 用 skill 自带 `scripts/audit_windows_ports.py`：既查实时 `netstat` 监听，也查 `%LOCALAPPDATA%\Programs\*/config/service.json` 里已登记但暂未运行的端口。
- 从 **10000–29999** 选未占用端口（不用 1–1023、不用 49152–65535 动态段）；端口集中写 `config/service.json`，启动 / 健康检查 / 页面提示都读它，不在多处硬编码。
- 首次安装未指定端口时，安装器自动在 10000–29999 选空闲端口并显示前后值、写入配置；**不结束占用进程**。显式指定端口冲突则报 PID + 中文提示后失败，不静默换号。升级保留已选端口。
- MVP 单端口：FastAPI 绑 `0.0.0.0:<port>`（带登录，直接对局域网）。若要 API 不暴露局域网，再引入便携 Nginx：Nginx `0.0.0.0:<webport>` 反代 FastAPI `127.0.0.1:<apiport>`（skill 的两端口模式），每个 Nginx 实例用自身安装目录的配置/prefix/PID/日志。

### 4.3 后端
- FastAPI + uvicorn，跑在便携 Python 上。
- v1 单用户：用 FastAPI `BackgroundTasks`（进程内）跑后台任务，**不引入 Redis**（单用户不需要分布式队列）。任务状态内存 + 落盘 JSON 防重启丢失。v2 上多用户时再引 arq + Redis（Windows 上用 Memurai）。
- 实时日志：SSE 推流，把现有脚本 `print` 重定向到任务日志缓冲，前端 `EventSource` 订阅。
- 脚本复用：v1 最省力是 `subprocess.run` 调现有 `main.py` / `run_pipeline.py` + 捕获 stdout 当日志流；后续重构 `process_files` / `run_pipeline` 子命令为可 import 函数（更干净，能拿结构化结果）。
- 内置预览托管：FastAPI StaticFiles 托管最新 `02_web_output/`，提供 console 内预览 URL（两路输出之一，见 §4.4）。

### 4.4 日历更新路径（两路：内置预览 + 推送对外平台）
- **现状**：对外日历由你们**自有的项目管理平台**托管 -- 把 HTML/JS 打 zip 上传到平台上的项目，平台给出对外分享 URL。平台也是自部署的。
- **操作台两路输出**（你选了「两者都要」）：
  1. **内置预览托管**：操作台用 FastAPI StaticFiles 托管最新 `02_web_output/`，给操作员一个 console 内预览 URL，用于发布前核对。Step 2 跑完即自动更新。
  2. **推送对外日历**：把 `02_web_output/` 打 zip 上传到项目管理平台的对应项目，更新对外分享 URL。
- **v1 走手动 zip（已确认可接受）**：「发布」按钮生成 zip + 下载链接 + 「打开平台上传页」按钮 + 文字步骤；操作员手动上传后回来点「标记已发布」。
- **已确认**：平台上传为**替换原文件、对外 URL 不变** -> 操作台配一次固定对外 URL，每次发布覆盖旧文件。
- **v2 可选**：若平台支持上传 API（允许程序自动传，而不只是网页手动传）且操作台服务器能网络连到平台，再升级为「一键 zip + 自动上传 + 回显」。v1 不依赖这两项，不阻塞。

### 4.5 密钥管理
- LLM key（DeepSeek + Ark）放安装目录内的配置/env（**仓库外、不进 git、不进系统环境变量**，因免管理员）。
- 前端只显示「已配置 / 未配置」，不接触明文。

### 4.6 数据与备份
- canonical + state 落 `data/`；覆盖 canonical 前存带时间戳 `.bak`（沿用 `dedup_canonical_excel.py` 习惯）。
- 定期备份 `data/` 目录。

### 4.7 登录
- v1 固定账号密码（配置文件），session cookie。内部工具够用，不做注册 / 找回。

---

## 5. 关键难点与风险

| 难点 | 风险 | 应对 |
|---|---|---|
| canonical 禁 openpyxl save | 上传回传若 openpyxl save 会损坏（弹修复框） | 上传校验用 `verify_canonical.py`；差异摘要只读 `read_only=True`；写回**直接落盘用户上传文件**，不重新生成（见 §6） |
| Chromium 打进便携包 | Playwright 浏览器不在 pip 里；装不上则演唱会采集不可用 | 打包时内置 Chromium 二进制 + `PLAYWRIGHT_BROWSERS_PATH` 指向包内；验证 `--only-concert` 能跑 |
| 政府站可达性 / SM4 变更 | `zwfw.mct.gov.cn` 不可达或接口变更致采集失败 | 服务器出站可达 mct.gov.cn；采集失败醒目日志（脚本已区分「真无数据」vs「抓取失败」） |
| 单文件并发 | 多人同时改 canonical 互相覆盖 | 编辑锁（v1）；v2 再做排队 |
| 长任务黑盒 | 用户以为卡死 | SSE 实时日志 + 阶段步骤器 + 计时 |
| LLM 成本与 key 泄露 | key 进前端或日志 | key 留安装目录配置；日志可显 token 用量，不显 key |
| 多项目端口冲突 | 与已有读者端项目抢端口 | `audit_windows_ports.py` 审计 + `service.json` 登记 |
| 对外日历推送依赖项目管理平台 | 平台上传方式未知（API / 仅 Web UI）；无 API 则只能半自动 | 先按手动 zip 保底；找同事确认有无 API，有则接一键上传 |

---

## 6. 上传回传 canonical 的写回策略（重点说明）

canonical 含 Excel 手工特性，**不能 openpyxl load+save**。v1 用「只读算差异 + 原样落盘」组合：

1. **直接落盘用户上传的文件**：用户在真桌面 Excel 里改的，文件本身完整。服务端**不重新生成**，直接把上传 xlsx 存为 canonical。零损坏风险。
2. **差异摘要**：用 openpyxl **只读**（`read_only=True`，不 save）读上传文件，与旧 canonical 比对，算「新增 / 删除 / 修改」明细给用户确认。
3. 上传时跑 `verify_canonical.py` 检查完整性，损坏即拒绝。
4. 「确认覆盖」二次确认后写回（先存 `.bak`）。
5. v2 网页编辑器：用 `add_dates_column.py` 那套 zipfile 解压改 sheet XML 原样压回的写法，避开 openpyxl save。

---

## 7. 分期建议

### MVP（先跑通，覆盖现有 run.bat 全部能力）
- 单用户编辑锁
- FastAPI + BackgroundTasks + SSE（无 Redis）
- 上传抽取、任务监控、下载/上传核对、生成日历、预览 + 推送更新
- 用 `package-windows-lan-app` skill 打离线包：便携 Python + 内置 Chromium + `安装.cmd` + 登录自启
- 端口审计 + `config/service.json`，与现有读者端共存
- 日历更新写到现有读者端服务目录，URL 不变

### v2（体验升级）
- 网页内事件编辑器（XML 写法）
- 多用户排队 + 细粒度锁
- 任务历史 / 用量统计完善
- arq + Redis（Memurai）分布式队列
- 便携 Nginx 两端口模式（API 不暴露局域网）

---

## 8. 部署前置检查清单（动手前先验证）

- [ ] 在服务器上跑 `audit_windows_ports.py`，为操作台选未占用端口（避开已有读者端项目）。
- [ ] 服务器有**出站**网络访问 DeepSeek / Ark API endpoint 和 `zwfw.mct.gov.cn`（LLM + 演唱会采集）。
- [x] 已确认：平台上传**替换原文件、对外 URL 不变**；操作台配一次固定对外 URL。
- [ ] v2 才需：找同事确认平台有无**上传 API**（程序自动传）、操作台服务器能否**网络连到平台**。v1 走手动 zip，不阻塞。
- [ ] LLM key 准备好（复用现有 DeepSeek + Ark）。
- [ ] canonical + state 数据从现有电脑迁到操作台 `data/`。
- [ ] 备份策略定好（`data/` 目录 + 频率）。
- 注：**无需在服务器装 Python 或 Chromium** -- 都打进便携包。

---

## 9. 打包验证清单（按 skill 要求）

- [ ] 打包前先本地跑通全流程一次（编译/测试/`git diff --check`），失败不生成伪成功包。
- [ ] ZIP 校验 SHA256；解压到临时目录确认入口 / 便携 Python / 应用 / 配置模板 / 清单完整，且 `.ps1` 数量为 0。
- [ ] 安装到 `%LOCALAPPDATA%\Programs\beijing-events-console-PackageTest-<version>`，验证复制 / 配置渲染 / 端口保存 / 升级数据保留。
- [ ] 再次端口审计；验证多项目可同时存在。
- [ ] 健康检查 + 浏览器验证管理入口、局域网入口、主要页面。
- [ ] 停测试服务时核对安装根目录和 PID；只删经解析确认的测试 / 临时目录，不用通配符。
- [ ] 最终 ZIP + SHA256 复制到交付目录；只有用户要求刷新才移除旧包。

---

## 10. 关联文档

- 《Web前端设计需求.md》- 交给前端设计模型的设计 brief。
- `skills/package-windows-lan-app/SKILL.md` - 部署打包的权威流程。
- 《使用说明.md》- 现有桌面流程说明（Web 化后逐步退役）。
