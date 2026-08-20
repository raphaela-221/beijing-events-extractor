"""Job registry。P0 用户面只登记 step1_concert_only；__dev_mock_longrun 仅供
开发压测日志/SSE/回放/虚拟滚动/摘要机制，不进 /api/jobs 列表。"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from .. import config


@dataclass
class Param:
    name: str
    type: str  # bool | string | text | int | date | month | enum | files | row_ref
    label: str
    help: str = ""
    default: Any = None
    choices: list[str] | None = None
    required: bool = False
    advanced: bool = False


@dataclass
class Job:
    id: str
    group: str
    label: str
    desc: str
    danger: str  # none | write_canonical | destructive
    needs_lock: bool
    stages: list[str]
    params: list[Param]
    artifacts: list[str] = field(default_factory=list)
    preflight: list[str] = field(default_factory=list)
    dry_run_pair: str | None = None
    admin_only: bool = False
    dev_only: bool = False  # 开发压测用，不进用户面列表

    def to_schema(self) -> dict:
        d = asdict(self)
        return d


_REGISTRY: dict[str, Job] = {}


def register(job: Job) -> None:
    _REGISTRY[job.id] = job


def get(job_id: str) -> Job | None:
    return _REGISTRY.get(job_id)


def list_jobs() -> list[Job]:
    """用户面列表：排除 dev_only。"""
    return [j for j in _REGISTRY.values() if not j.dev_only]


# ---- argv 构造（每个 job 一份）----
def _append_input_dir(argv: list[str], upload_id: object) -> None:
    """files 参数 upload_id -> --input-dir。空则不加（脚本用默认 01_raw_input）。"""
    if upload_id:
        argv += ["--input-dir", str(resolve_upload_dir(str(upload_id)))]


def _append_extract_opts(argv: list[str], params: dict) -> None:
    """文件提取类参数：mode/category/topic/extra-info。"""
    mode = params.get("mode")
    if mode and mode != "auto":
        argv += ["--mode", str(mode)]
    if params.get("category"):
        argv += ["--category", str(params["category"])]
    if params.get("topic"):
        argv += ["--topic", str(params["topic"])]
    if params.get("extra_info"):
        argv += ["--extra-info", str(params["extra_info"])]


def _append_concert_opts(argv: list[str], params: dict) -> None:
    """演唱会采集参数。"""
    if params.get("concert-force"):
        argv.append("--concert-force")
    if params.get("concert-start"):
        argv += ["--concert-start", str(params["concert-start"])]
    if params.get("concert-end"):
        argv += ["--concert-end", str(params["concert-end"])]
    vs = params.get("concert-venue-size")
    if vs and vs != "medium":
        argv += ["--concert-venue-size", str(vs)]


def _build_step1_concert_only(params: dict) -> list[str]:
    argv = [sys.executable, str(config.STEP1_MAIN), "--only-concert"]
    if params.get("concert-force"):
        argv.append("--concert-force")
    if params.get("concert-start"):
        argv += ["--concert-start", str(params["concert-start"])]
    if params.get("concert-end"):
        argv += ["--concert-end", str(params["concert-end"])]
    vs = params.get("concert-venue-size")
    if vs and vs != "medium":
        argv += ["--concert-venue-size", str(vs)]
    return argv


def _build_step1_full(params: dict) -> list[str]:
    """全量：处理上传文件 + 采集演唱会（--concert）。"""
    argv = [sys.executable, str(config.STEP1_MAIN), "--concert"]
    _append_input_dir(argv, params.get("input_files"))
    _append_extract_opts(argv, params)
    _append_concert_opts(argv, params)
    return argv


def _build_step1_input_only(params: dict) -> list[str]:
    """只处理文件（--only-input），不采集演唱会。必须上传文件。"""
    upload_id = params.get("input_files")
    if not upload_id:
        raise ValueError("「只处理上传文件」需要先上传文件")
    argv = [sys.executable, str(config.STEP1_MAIN), "--only-input"]
    _append_input_dir(argv, upload_id)
    _append_extract_opts(argv, params)
    return argv


def _build_step2_all(params: dict) -> list[str]:
    """整跑：extract + themes + calendar + package（run_pipeline.py all）。"""
    argv = [sys.executable, str(config.CALENDAR_DIR / "run_pipeline.py"), "all", "--themes"]
    if params.get("auto_package") is not False:  # 默认 True
        argv.append("--package")
    if params.get("year"):
        argv += ["--year", str(params["year"])]
    if params.get("force_month"):
        argv += ["--month", str(params["force_month"])]
    return argv


def _build_step2_themes(params: dict) -> list[str]:
    """分步②：生成月度主题（Ark，增量或强制单月）。"""
    argv = [sys.executable, str(config.CALENDAR_DIR / "run_pipeline.py"), "themes"]
    if params.get("year"):
        argv += ["--year", str(params["year"])]
    if params.get("force_month"):
        argv += ["--month", str(params["force_month"])]
    return argv


def _build_step2_extract(params: dict) -> list[str]:
    """分步①：从 canonical 抽取 High 事件。"""
    return [sys.executable, str(config.CALENDAR_DIR / "run_pipeline.py"), "extract"]


def _build_step2_calendar(params: dict) -> list[str]:
    """分步③：校验 calendar 页面文件齐全。"""
    return [sys.executable, str(config.CALENDAR_DIR / "run_pipeline.py"), "calendar"]


def _build_step2_package(params: dict) -> list[str]:
    """分步④：打包分享文件到 02_web_output/。"""
    return [sys.executable, str(config.CALENDAR_DIR / "run_pipeline.py"), "package"]


def _build_mock(params: dict) -> list[str]:
    lines = str(params.get("lines", 5000))
    delay = str(params.get("delay", 0.005))
    return [sys.executable, str(config.BACKEND_DIR / "dev" / "mock_longrun.py"), lines, delay]


# ---- canonical 维护类（工具箱）----
def _build_dates_enrich_dry(params: dict) -> list[str]:
    """Dates 自动抽取试运行：LLM 抽离散场次日期，只打印不写。"""
    return [sys.executable, str(config.ENRICH_DATES_MAIN), "--dry-run"]


def _build_dates_enrich_write(params: dict) -> list[str]:
    """Dates 自动抽取写入：零损耗 XML 写到 R 列。"""
    return [sys.executable, str(config.ENRICH_DATES_MAIN)]


def _build_dates_add_row(params: dict) -> list[str]:
    """Dates 手动补单行：指定行号 + 值，零损耗 XML 写。"""
    row = params.get("row")
    value = params.get("value")
    if not row or not value:
        raise ValueError("手动补单行需要行号和 Dates 值")
    return [
        sys.executable, str(config.CALENDAR_DIR / "add_dates_column.py"),
        "--excel", str(config.CANONICAL_PATH),
        "--row", str(int(row)), "--value", str(value),
    ]


def _build_canonical_dedup_dry(params: dict) -> list[str]:
    """canonical 去重试运行：只报告不写。"""
    return [sys.executable, str(config.CALENDAR_DIR / "dedup_canonical_excel.py"), "--dry-run"]


def _build_canonical_dedup_write(params: dict) -> list[str]:
    """canonical 去重写入：删除重复行；可选 prune-malformed 删格式异常行。"""
    argv = [sys.executable, str(config.CALENDAR_DIR / "dedup_canonical_excel.py")]
    if params.get("prune_malformed"):
        argv.append("--prune-malformed")
    return argv


def _build_canonical_verify(params: dict) -> list[str]:
    """结构守卫自检：检测 openpyxl 往返损坏。"""
    return [sys.executable, str(config.CALENDAR_DIR / "verify_canonical.py"), "--quiet"]


def _build_canonical_export_raw(params: dict) -> list[str]:
    """用源 Excel 铺底：上传干净源 xlsx 覆盖 canonical（结构损坏后恢复用）。"""
    upload_id = params.get("source_file")
    if not upload_id:
        raise ValueError("铺底需要上传源 Excel")
    d = resolve_upload_dir(str(upload_id))
    xlsx = next(d.glob("*.xlsx"), None)
    if not xlsx:
        raise ValueError("上传目录无 xlsx 文件")
    return [
        sys.executable, str(config.CALENDAR_DIR / "export_raw_xlsx.py"),
        "--source", str(xlsx),
        "--output-dir", str(config.PROJECT_ROOT / "01_event_list_output"),
    ]


_BUILDERS: dict[str, Callable[[dict], list[str]]] = {
    "step1_concert_only": _build_step1_concert_only,
    "step1_full": _build_step1_full,
    "step1_input_only": _build_step1_input_only,
    "step2_all": _build_step2_all,
    "step2_themes": _build_step2_themes,
    "step2_extract": _build_step2_extract,
    "step2_calendar": _build_step2_calendar,
    "step2_package": _build_step2_package,
    "dates_enrich_dry": _build_dates_enrich_dry,
    "dates_enrich_write": _build_dates_enrich_write,
    "dates_add_row": _build_dates_add_row,
    "canonical_dedup_dry": _build_canonical_dedup_dry,
    "canonical_dedup_write": _build_canonical_dedup_write,
    "canonical_verify": _build_canonical_verify,
    "canonical_export_raw": _build_canonical_export_raw,
    "__dev_mock_longrun": _build_mock,
}


def build_argv(job: Job, params: dict) -> list[str]:
    return _BUILDERS[job.id](params)


# ---- files 参数解析 ----
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{1,64}$")


def resolve_upload_dir(upload_id: str) -> Path:
    """把 type=files 参数的 upload_id 解析成磁盘目录路径。

    builder 把该目录作为 --input-dir 传给脚本（脚本读目录下全部文件）。
    upload_id 必须是 hex（防路径穿越）。
    """
    if not _UPLOAD_ID_RE.match(upload_id or ""):
        raise ValueError(f"非法 upload_id: {upload_id!r}")
    p = config.UPLOADS_DIR / upload_id
    if not p.is_dir():
        raise FileNotFoundError(f"上传目录不存在: {upload_id}")
    return p


# ---- preflight ----
def run_preflight(job: Job) -> list[str]:
    """返回失败检查 id 列表。env_keys：DeepSeek/Ark 至少一个非空。"""
    problems: list[str] = []
    for check in job.preflight:
        if check == "env_keys":
            import os

            ds = os.getenv("OPENAI_API_KEY", "").strip()
            ark = os.getenv("ARK_API_KEY", "").strip()
            if not ds and not ark:
                problems.append("env_keys")
    return problems


# ---- P0 注册 ----
register(
    Job(
        id="step1_concert_only",
        group="抽取",
        label="只采集演唱会",
        desc="从文化和旅游部政务服务平台采集北京地区演唱会信息，合并写入 Events List.xlsx。运行前自动备份。",
        danger="write_canonical",
        needs_lock=True,
        stages=["列表页采集", "详情页采集", "过滤", "合并去重", "写入 Excel"],
        params=[
            Param(
                name="concert-force",
                type="bool",
                label="强制重抓",
                help="不跳过已采集过的场次，全部重新抓取一次",
                default=False,
                advanced=True,
            ),
            Param(
                name="concert-start",
                type="date",
                label="演唱会日期范围·开始",
                help="格式 YYYY-MM-DD，默认过去 2 个月",
                default="",
                advanced=True,
            ),
            Param(
                name="concert-end",
                type="date",
                label="演唱会日期范围·结束",
                help="格式 YYYY-MM-DD，默认未来 2 年",
                default="",
                advanced=True,
            ),
            Param(
                name="concert-venue-size",
                type="enum",
                label="最小场馆规模",
                help="medium 默认排除小型 LiveHouse；large 只保留大型场馆；small 保留全部",
                default="medium",
                choices=["small", "medium", "large"],
                advanced=True,
            ),
        ],
        artifacts=["01_event_list_output/Events List.xlsx"],
        preflight=["env_keys"],
    )
)

# ---- P1.3 Step1 全量 / 只文件 ----
register(
    Job(
        id="step1_full",
        group="抽取",
        label="全量抽取",
        desc="处理上传文件 + 同时采集北京演唱会。月度例行首选，覆盖最全。运行前自动备份。",
        danger="write_canonical",
        needs_lock=True,
        stages=["读取文件", "LLM 抽取", "过滤去重", "演唱会采集", "合并写入"],
        params=[
            Param(
                name="input_files",
                type="files",
                label="上传原始监测文件",
                help="支持 xlsx/xls/csv/txt/json，可同时选择多个。不上传则用默认 01_raw_input 目录",
                default=None,
                advanced=False,
            ),
            Param(
                name="mode",
                type="enum",
                label="提取模式",
                help="auto 自动判断；spring_break 中小学春秋假；event_summary 事件总结",
                default="auto",
                choices=["auto", "spring_break", "event_summary"],
                advanced=True,
            ),
            Param(
                name="category",
                type="string",
                label="手动指定分类",
                help="如『大型会议和展览』，留空自动推断",
                default="",
                advanced=True,
            ),
            Param(
                name="topic",
                type="string",
                label="提取主题补充描述",
                help="给本次提取的额外说明",
                default="",
                advanced=True,
            ),
            Param(
                name="extra_info",
                type="text",
                label="提取要求补充",
                help="对提取要求的补充说明",
                default="",
                advanced=True,
            ),
            Param(
                name="concert-force",
                type="bool",
                label="强制重抓",
                help="不跳过已采集过的场次，全部重新抓取一次",
                default=False,
                advanced=True,
            ),
            Param(
                name="concert-start",
                type="date",
                label="演唱会日期范围·开始",
                help="格式 YYYY-MM-DD，默认过去 2 个月",
                default="",
                advanced=True,
            ),
            Param(
                name="concert-end",
                type="date",
                label="演唱会日期范围·结束",
                help="格式 YYYY-MM-DD，默认未来 2 年",
                default="",
                advanced=True,
            ),
            Param(
                name="concert-venue-size",
                type="enum",
                label="最小场馆规模",
                help="medium 默认排除小型 LiveHouse；large 只保留大型场馆；small 保留全部",
                default="medium",
                choices=["small", "medium", "large"],
                advanced=True,
            ),
        ],
        artifacts=["01_event_list_output/Events List.xlsx"],
        preflight=["env_keys"],
    )
)

register(
    Job(
        id="step1_input_only",
        group="抽取",
        label="只处理上传文件",
        desc="只处理上传的监测文件，跳过演唱会采集。政务网站不可达时的备选。运行前自动备份。",
        danger="write_canonical",
        needs_lock=True,
        stages=["读取文件", "LLM 抽取", "过滤去重", "合并写入"],
        params=[
            Param(
                name="input_files",
                type="files",
                label="上传原始监测文件",
                help="支持 xlsx/xls/csv/txt/json，可同时选择多个",
                default=None,
                required=True,
                advanced=False,
            ),
            Param(
                name="mode",
                type="enum",
                label="提取模式",
                help="auto 自动判断；spring_break 中小学春秋假；event_summary 事件总结",
                default="auto",
                choices=["auto", "spring_break", "event_summary"],
                advanced=True,
            ),
            Param(
                name="category",
                type="string",
                label="手动指定分类",
                help="如『大型会议和展览』，留空自动推断",
                default="",
                advanced=True,
            ),
            Param(
                name="topic",
                type="string",
                label="提取主题补充描述",
                help="给本次提取的额外说明",
                default="",
                advanced=True,
            ),
            Param(
                name="extra_info",
                type="text",
                label="提取要求补充",
                help="对提取要求的补充说明",
                default="",
                advanced=True,
            ),
        ],
        artifacts=["01_event_list_output/Events List.xlsx"],
        preflight=["env_keys"],
    )
)

# ---- P1.5 Step2 生成日历（整跑 + 分步四步）----
register(
    Job(
        id="step2_all",
        group="生成日历",
        label="一键整跑",
        desc="从人工审核清单抽取 High 事件，生成月度主题与日历页面，并打包发布文件。月度例行首选。",
        danger="none",
        needs_lock=False,
        stages=["抽取 High 事件", "生成月度主题", "校验页面", "打包发布"],
        params=[
            Param(
                name="year",
                type="int",
                label="年份",
                help="留空用当前年",
                default=2026,
                advanced=False,
            ),
            Param(
                name="force_month",
                type="month",
                label="强制重新生成月份（可选）",
                help="留空则只重算 changed_months 里的月份",
                default="",
                advanced=False,
            ),
            Param(
                name="auto_package",
                type="bool",
                label="跑完自动打包发布文件",
                help="生成 02_web_output/ 供预览与发布页使用",
                default=True,
                advanced=False,
            ),
        ],
        artifacts=["02_web_output/"],
        preflight=["env_keys"],
    )
)

register(
    Job(
        id="step2_extract",
        group="生成日历",
        label="抽取 High 事件",
        desc="从 canonical Events List.xlsx 抽取 High 事件，生成 events_data.js。",
        danger="none",
        needs_lock=False,
        stages=["抽取 High 事件"],
        params=[],
        artifacts=["02_calendar/events_data.js"],
        preflight=[],
    )
)

register(
    Job(
        id="step2_themes",
        group="生成日历",
        label="生成月度主题",
        desc="调 Ark 生成/刷新月度主题。增量：仅 changed_months 调模型，或强制单月。",
        danger="none",
        needs_lock=False,
        stages=["生成月度主题"],
        params=[
            Param(
                name="year",
                type="int",
                label="年份",
                help="留空用当前年",
                default=2026,
                advanced=False,
            ),
            Param(
                name="force_month",
                type="month",
                label="强制重新生成月份（可选）",
                help="留空则只重算 changed_months 里的月份",
                default="",
                advanced=False,
            ),
        ],
        artifacts=[],
        preflight=["env_keys"],
    )
)

register(
    Job(
        id="step2_calendar",
        group="生成日历",
        label="校验页面文件齐全",
        desc="校验 calendar 页面文件（index/month/timeline/events_data 等）齐全可用。",
        danger="none",
        needs_lock=False,
        stages=["校验页面"],
        params=[],
        artifacts=[],
        preflight=[],
    )
)

register(
    Job(
        id="step2_package",
        group="生成日历",
        label="打包分享文件",
        desc="把 calendar 页面打包到 02_web_output/ 供预览与发布。",
        danger="none",
        needs_lock=False,
        stages=["打包发布"],
        params=[],
        artifacts=["02_web_output/"],
        preflight=[],
    )
)

# ---- P2-B canonical 维护（工具箱分组）----
register(
    Job(
        id="dates_enrich_dry",
        group="canonical 维护",
        label="Dates 列自动抽取（试运行）",
        desc="LLM 从事件描述抽取演唱会离散场次日期，只预览不写入。用于写入前核对将给哪些行写什么值。",
        danger="none",
        needs_lock=False,
        stages=["LLM 抽取 Dates", "打印预览"],
        params=[],
        preflight=["env_keys"],
    )
)

register(
    Job(
        id="dates_enrich_write",
        group="canonical 维护",
        label="Dates 列自动抽取（写入）",
        desc="将试运行确认过的离散场次日期零损耗 XML 写到 R 列（表外，避开 table 范围）。建议先跑试运行核对。",
        danger="write_canonical",
        needs_lock=True,
        stages=["LLM 抽取 Dates", "写入 Dates 列"],
        params=[],
        artifacts=["01_event_list_output/Events List.xlsx"],
        preflight=["env_keys"],
        dry_run_pair="dates_enrich_dry",
    )
)

register(
    Job(
        id="dates_add_row",
        group="canonical 维护",
        label="Dates 手动补单行",
        desc="enrich 抽不出的行（反向排除/跨月/点分日期），手动指定行号和 Dates 值。零损耗 XML 写。",
        danger="write_canonical",
        needs_lock=True,
        stages=["写入 Dates 列"],
        params=[
            Param(
                name="row",
                type="row_ref",
                label="行号",
                help="Excel 中的行号（含表头则数据从第 2 行起）；输入后下方回显该行内容供核对",
                default=None,
                required=True,
                advanced=False,
            ),
            Param(
                name="value",
                type="string",
                label="Dates 值",
                help="同年同月省略年份，系统按 Start Date 取年（如 5.9-10 或 5.9,5.10）；跨年月须写完整如 2026-08-30~2026-09-02。多个用英文逗号分隔",
                default="",
                required=True,
                advanced=False,
            ),
        ],
        artifacts=["01_event_list_output/Events List.xlsx"],
        preflight=[],
    )
)

register(
    Job(
        id="canonical_dedup_dry",
        group="canonical 维护",
        label="canonical 去重（试运行）",
        desc="检测重复事件行，只报告不写回。跨运行/跨来源的重复在这里统一捕获。",
        danger="none",
        needs_lock=False,
        stages=["扫描重复行", "打印报告"],
        params=[],
        preflight=[],
    )
)

register(
    Job(
        id="canonical_dedup_write",
        group="canonical 维护",
        label="canonical 去重（写入）",
        desc="删除重复行；勾选 prune-malformed 会额外删除格式异常的行（只有 Link 无标题/日期/分类）。建议先跑试运行。管理员限定。",
        danger="destructive",
        needs_lock=True,
        stages=["删除重复行"],
        params=[
            Param(
                name="prune_malformed",
                type="bool",
                label="同时删除格式异常的行",
                help="会删除只有 Link、无标题/日期/分类的行，谨慎勾选",
                default=False,
                advanced=False,
            ),
        ],
        artifacts=["01_event_list_output/Events List.xlsx"],
        preflight=[],
        dry_run_pair="canonical_dedup_dry",
        admin_only=True,
        dev_only=True,  # 暂禁用：dedup 脚本用 openpyxl save 会损坏 canonical（违反铁律），待改 XML 删行方案后再开放
    )
)

register(
    Job(
        id="canonical_verify",
        group="canonical 维护",
        label="结构守卫自检",
        desc="检测 canonical 是否被 openpyxl 往返损坏（sharedStrings/printerSettings/table 错位）。损坏则退出码 1。",
        danger="none",
        needs_lock=False,
        stages=["结构检测"],
        params=[],
        preflight=[],
    )
)

register(
    Job(
        id="canonical_export_raw",
        group="canonical 维护",
        label="用源 Excel 铺底",
        desc="用上传的干净源 Excel 覆盖当前 canonical。用于结构损坏后的恢复重铺。破坏性，管理员限定。",
        danger="destructive",
        needs_lock=True,
        stages=["复制源文件覆盖 canonical"],
        params=[
            Param(
                name="source_file",
                type="files",
                label="上传干净源 Excel",
                help="结构正常的源 xlsx，将覆盖 01_event_list_output/Events List.xlsx",
                default=None,
                required=True,
                advanced=False,
            ),
        ],
        artifacts=["01_event_list_output/Events List.xlsx"],
        preflight=[],
        admin_only=True,
    )
)

# dev 压测：产生 N 行日志 + concert/llm 汇总块，用于验虚拟滚动/回放/取消/摘要
register(
    Job(
        id="__dev_mock_longrun",
        group="抽取",
        label="[dev] 长跑压测",
        desc="开发用：产生大量日志行 + 汇总块，压测日志底座。不进用户面。",
        danger="none",
        needs_lock=True,
        stages=["列表页采集", "详情页采集", "过滤", "合并去重", "写入 Excel"],
        params=[
            Param(name="lines", type="int", label="日志行数", default=5000, advanced=False),
            Param(name="delay", type="string", label="每段间隔(秒)", default="0.005", advanced=True),
        ],
        preflight=[],
        dev_only=True,
    )
)
