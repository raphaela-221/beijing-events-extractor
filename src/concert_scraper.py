"""
北京演唱会信息抓取工具 — Playwright 版

从文化和旅游部政务服务平台抓取北京地区涉外营业性演出活动信息，
筛选出演唱会类活动并转换为标准事件格式。
支持增量更新（跳过已采集过的 URL）。
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from urllib.parse import quote

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from openai import OpenAI

logger = logging.getLogger(__name__)

# 文化和旅游部政务服务平台 - 全国涉外营业性演出活动公示
BASE_LIST_URL = "https://zwfw.mct.gov.cn/wycx/qgswyyxychd/qgswyyxychdjg/"

# 状态文件路径
STATE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "state",
    "concert_scrape_state.json"
)

# 排除的非演唱会关键词
EXCLUDE_KEYWORDS = [
    "音乐会", "音乐节", "交响乐", "管弦乐", "合唱团",
    "舞剧", "芭蕾", "话剧", "歌剧", "音乐剧", "四重奏", "室内乐",
    "独奏", "协奏曲", "朗诵", "杂技", "马戏"
]

# 大型场馆关键词
LARGE_VENUE_KEYWORDS = [
    "鸟巢", "国家体育场", "国家体育馆", "首都体育馆",
    "五棵松体育馆", "华熙", "润百颜中心",
    "工人体育场", "工体", "凯迪拉克中心",
    "奥体中心", "水立方", "国家游泳中心",
    "展览馆", "会展中心", "体育中心",
]

# 小型场馆关键词（用于排除）
SMALL_VENUE_KEYWORDS = [
    "剧场", "剧院", "酒吧", "livehouse", "live house",
    "仓库", "蛙厂", "开花豆", "大华", "微声万象",
    "爱乐汇", "战马时代", "正在映画",
]

# 场馆规模优先级
SIZE_ORDER = {"small": 0, "medium": 1, "large": 2}


def _get_venue_size(venue: str) -> str:
    """判断演出场所规模。"""
    venue_lower = venue.lower()
    for kw in LARGE_VENUE_KEYWORDS:
        if kw in venue:
            return "large"
    for kw in SMALL_VENUE_KEYWORDS:
        if kw in venue_lower:
            return "small"
    if "体育馆" in venue or "体育场" in venue:
        return "large"
    return "medium"


def _is_concert(name: str) -> bool:
    """根据名称判断是否为演唱会。"""
    name_lower = name.lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in name:
            return False
    if "演唱会" in name or "concert" in name_lower:
        return True
    return False


def _get_llm_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    import httpx
    bypass_proxy = os.getenv("OPENAI_BYPASS_PROXY", "1") == "1"
    http_client = httpx.Client(
        timeout=120.0,
        trust_env=not bypass_proxy,
    )

    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        http_client=http_client,
    )


def _fallback_english_title(name: str) -> str:
    text = name.strip()
    replacements = {
        "演唱会": "Concert",
        "巡回": "Tour",
        "北京站": "Beijing Stop",
        "北京专场": "Beijing Show",
        "北京": "Beijing",
        "现场": "Live",
    }
    for zh, en in replacements.items():
        text = text.replace(zh, en)
    return text


def _translate_concert_names(names: List[str]) -> Dict[str, str]:
    unique_names = [name for name in dict.fromkeys(n.strip() for n in names) if name]
    if not unique_names:
        return {}

    fallback = {name: _fallback_english_title(name) for name in unique_names}

    try:
        client = _get_llm_client()
        model = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Translate Chinese concert event titles into fluent English event title phrases. Keep artist names and official English tour names. Output strict JSON only.",
                },
                {
                    "role": "user",
                    "content": json.dumps({"titles": unique_names}, ensure_ascii=False),
                },
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        translations = data.get("translations", data)
        result = fallback.copy()
        if isinstance(translations, list):
            for name, translated in zip(unique_names, translations):
                translated = str(translated).strip()
                if translated:
                    result[name] = translated
            return result
        if isinstance(translations, dict):
            translated_values = translations.get("titles")
            if isinstance(translated_values, list):
                for name, translated in zip(unique_names, translated_values):
                    translated = str(translated).strip()
                    if translated:
                        result[name] = translated
                return result
            for name in unique_names:
                translated = str(translations.get(name, "")).strip()
                if translated:
                    result[name] = translated
        return result
    except Exception as ex:
        logger.warning(f"Failed to translate concert names, using fallback titles: {ex}")
        return fallback


# ============================================================
# 状态持久化
# ============================================================

def _load_state() -> dict:
    """读取采集状态文件。"""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load scrape state: {e}")
    return {"last_scrape_date": "", "scraped_urls": []}


def _save_state(state: dict) -> None:
    """保存采集状态到文件。"""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save scrape state: {e}")


# ============================================================
# Playwright 辅助函数
# ============================================================

def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    days_in_month = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(dt.day, days_in_month[month - 1])
    return dt.replace(year=year, month=month, day=day)


def _build_ranges_by_step(start_dt: datetime, end_dt: datetime, step: str) -> List[tuple]:
    ranges = []
    current = start_dt

    while current <= end_dt:
        if step == "six_month":
            chunk_end = min(_add_months(current, 6) - timedelta(days=1), end_dt)
        elif step == "month":
            chunk_end = min(_add_months(current, 1) - timedelta(days=1), end_dt)
        else:
            days = {"7d": 7, "3d": 3, "2d": 2, "1d": 1}[step]
            chunk_end = min(current + timedelta(days=days - 1), end_dt)

        ranges.append((current, chunk_end, step))
        current = chunk_end + timedelta(days=1)

    return ranges


def _build_date_ranges(start_dt: datetime, end_dt: datetime) -> List[tuple]:
    """Build initial query ranges by time bucket: past=3d, near future=month, far future=6 months."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    six_month_mark = _add_months(today, 6)
    ranges = []

    if start_dt < today:
        past_end = min(end_dt, today - timedelta(days=1))
        if start_dt <= past_end:
            ranges.extend(_build_ranges_by_step(start_dt, past_end, "3d"))

    near_start = max(start_dt, today)
    near_end = min(end_dt, six_month_mark)
    if near_start <= near_end:
        ranges.extend(_build_ranges_by_step(near_start, near_end, "month"))

    far_start = max(start_dt, six_month_mark + timedelta(days=1))
    if far_start <= end_dt:
        ranges.extend(_build_ranges_by_step(far_start, end_dt, "six_month"))

    return ranges


def _split_range(start_dt: datetime, end_dt: datetime, step: str) -> List[tuple]:
    next_step = {
        "six_month": "month",
        "month": "7d",
        "7d": "3d",
        "3d": "2d",
        "2d": "1d",
    }.get(step)

    if not next_step:
        return []
    return _build_ranges_by_step(start_dt, end_dt, next_step)


def _scrape_list_items(page, start_date: str, end_date: str) -> List[Dict]:
    """
    用 Playwright 抓取指定日期范围的列表页，返回详情链接列表。
    分段策略：过去按3天，未来6个月内按月，6个月以后按半年；超过15条逐级拆小。
    """
    all_items = []
    seen_urls = set()

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    ranges = _build_date_ranges(start_dt, end_dt)

    while ranges:
        s_dt, e_dt, step = ranges.pop(0)
        s = s_dt.strftime("%Y-%m-%d")
        e = e_dt.strftime("%Y-%m-%d")

        # 构建列表页 URL
        url = (
            f"{BASE_LIST_URL}"
            f"?qgswperformancePlace1={quote('北京')}"
            f"&qgswperformingBeginTime={s}"
            f"&qgswperformingEndTime={e}"
        )

        try:
            logger.info(f"Fetching list: {s} to {e}")
            page.goto(url, wait_until="networkidle", timeout=30000)

            # 等待表格渲染（等待 tbody 中有数据行）
            page.wait_for_selector(".table_cons tr", timeout=10000)

            # 提取总记录数
            total_text = page.inner_text("body")
            total_match = re.search(r"共\s*(\d+)\s*条", total_text)
            total_count = int(total_match.group(1)) if total_match else 0

            # 如果超过15条且范围大于1天，逐级拆分；1天仍超过15条则接受第一页
            if total_count > 15 and (e_dt - s_dt).days >= 1:
                smaller_ranges = _split_range(s_dt, e_dt, step)
                if smaller_ranges:
                    logger.info(
                        f"Range {s}~{e} ({step}) has {total_count} items, "
                        f"splitting into {smaller_ranges[0][2]} ranges"
                    )
                    ranges = smaller_ranges + ranges
                    continue

            # 提取列表数据
            rows = page.query_selector_all(".table_cons tr")
            for row in rows[1:]:  # Skip header row
                cells = row.query_selector_all("td")
                if len(cells) < 2:
                    continue

                link_el = cells[0].query_selector("a")
                if not link_el:
                    continue

                name = link_el.inner_text().strip()
                href = link_el.get_attribute("href") or ""
                date_text = cells[1].inner_text().strip()

                # 构建完整 URL
                if href.startswith("./xq/"):
                    detail_url = BASE_LIST_URL + href[2:]  # Remove "./"
                elif href.startswith("/"):
                    detail_url = "https://zwfw.mct.gov.cn" + href
                elif href.startswith("http"):
                    detail_url = href
                else:
                    detail_url = BASE_LIST_URL + href

                # 提取日期
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
                list_date = date_match.group(1) if date_match else ""

                if detail_url not in seen_urls:
                    seen_urls.add(detail_url)
                    all_items.append({
                        "url": detail_url,
                        "name": name,
                        "date": list_date,
                    })

            logger.info(f"Found {len(rows) - 1} items for {s}~{e}")

        except Exception as ex:
            logger.error(f"Error fetching list for {s} to {e}: {ex}")

    return all_items


def _scrape_detail_page(page, url: str) -> Optional[Dict]:
    """用 Playwright + BeautifulSoup 抓取详情页。"""
    try:
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        # 查找详情表格
        table = soup.find("table", class_="list")
        if not table:
            logger.warning(f"No detail table found at {url}")
            return None

        data = {
            "name": "",
            "location": "",
            "start_date": "",
            "end_date": "",
            "venue": "",
            "organizer": "",
            "approval_unit": "",
            "approval_time": "",
            "document_number": "",
            "url": url,
        }

        field_map = {
            "演出名称：": "name",
            "演出地：": "location",
            "演出场所：": "venue",
            "报批单位：": "organizer",
            "审批单位：": "approval_unit",
            "批复时间：": "approval_time",
            "文号：": "document_number",
        }

        for tr in table.find_all("tr"):
            tds = tr.find_all(["td", "th"])
            if len(tds) < 2:
                continue

            key = tds[0].get_text(strip=True)
            value = tds[1].get_text(strip=True)

            # 演出时间特殊处理
            if "演出时间：" in key:
                m = re.search(r"(\d{4}-\d{2}-\d{2})\s*至\s*(\d{4}-\d{2}-\d{2})", value)
                if m:
                    data["start_date"] = m.group(1)
                    data["end_date"] = m.group(2)
                else:
                    m2 = re.search(r"(\d{4}-\d{2}-\d{2})", value)
                    if m2:
                        data["start_date"] = m2.group(1)
                        data["end_date"] = m2.group(1)
                continue

            for keyword, field_name in field_map.items():
                if keyword in key:
                    data[field_name] = value
                    break

        return data

    except Exception as ex:
        logger.error(f"Error fetching detail {url}: {ex}")
        return None


# ============================================================
# 核心采集逻辑
# ============================================================

def _scrape_concerts_impl(
    start_date: str,
    end_date: str,
    incremental: bool = False,
    min_venue_size: str = "medium",
) -> List[Dict]:
    """
    抓取北京演唱会信息的核心逻辑。

    参数:
        start_date: 查询起始日期 (YYYY-MM-DD)
        end_date: 查询截止日期 (YYYY-MM-DD)
        incremental: 是否增量模式（跳过已采集的URL）
        min_venue_size: 最小场馆规模 "small"|"medium"|"large"

    返回:
        标准事件格式（与本项目 extractor.py 输出兼容）的列表
    """
    # 加载已采集 URL
    state = _load_state()
    known_urls = set(state.get("scraped_urls", [])) if incremental else set()
    logger.info(f"Known URLs: {len(known_urls)}")

    concerts = []
    new_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # 1. 采集列表页
            logger.info(f"Fetching list from {start_date} to {end_date}...")
            items = _scrape_list_items(page, start_date, end_date)
            logger.info(f"Total list items: {len(items)}")

            # 2. 列表页关键词过滤 + URL 去重
            filtered = []
            for item in items:
                if not _is_concert(item["name"]):
                    logger.debug(f"Excluded by keyword: {item['name']}")
                    continue
                if incremental and item["url"] in known_urls:
                    logger.debug(f"Already scraped: {item['url']}")
                    continue
                filtered.append(item)

            logger.info(f"After keyword filter: {len(filtered)} concerts to fetch")

            # 3. 采集详情页
            for item in filtered:
                detail = _scrape_detail_page(page, item["url"])
                if not detail:
                    logger.info(f"Dropped concert candidate: detail parse failed | {item['name']} | {item['url']}")
                    continue

                location = detail.get("location", "")
                if "北京" not in location:
                    logger.info(
                        f"Dropped concert candidate: non-Beijing or missing location | "
                        f"{detail.get('name') or item['name']} | location={location}"
                    )
                    continue

                # 场馆规模过滤
                venue = detail.get("venue", "")
                venue_size = _get_venue_size(venue)
                min_level = SIZE_ORDER.get(min_venue_size, 1)
                if SIZE_ORDER.get(venue_size, 0) < min_level:
                    logger.info(
                        f"Dropped concert candidate: venue too small | "
                        f"{detail.get('name') or item['name']} | venue={venue} | size={venue_size}"
                    )
                    continue

                concerts.append(detail)
                new_urls.append(item["url"])
                logger.info(
                    f"Concert: {detail['name']} @ {detail['venue']} "
                    f"({detail['start_date']} ~ {detail['end_date']})"
                )

        finally:
            browser.close()

    # 4. 更新状态
    if new_urls:
        all_urls = known_urls | set(new_urls)
        state["last_scrape_date"] = datetime.now().strftime("%Y-%m-%d")
        state["scraped_urls"] = list(all_urls)
        _save_state(state)
        logger.info(f"State updated: {len(new_urls)} new URLs, total {len(all_urls)}")

    return _dedupe_concert_details(concerts)


def _dedupe_concert_details(concerts: List[Dict]) -> List[Dict]:
    """按演出名称+场馆合并同一场多日演唱会。"""
    merged = {}
    for concert in concerts:
        key = (
            concert.get("name", "").strip(),
            concert.get("venue", "").strip(),
        )
        if key not in merged:
            merged[key] = concert
            continue

        existing = merged[key]
        dates = [
            d for d in [
                existing.get("start_date"),
                existing.get("end_date"),
                concert.get("start_date"),
                concert.get("end_date"),
            ]
            if d
        ]
        if dates:
            existing["start_date"] = min(dates)
            existing["end_date"] = max(dates)

    return list(merged.values())


def scrape_beijing_concerts(
    incremental: bool = True,
    start_date: str = "",
    end_date: str = "",
    min_venue_size: str = "medium",
) -> List[Dict]:
    """
    抓取北京演唱会信息并转换为标准事件格式。

    参数:
        incremental: 是否增量模式（默认True，跳过已采集URL）
        start_date: 查询开始日期（不传则默认过去2个月）
        end_date: 查询结束日期（不传则默认未来不设限，但实际数据有限）
        min_venue_size: 最小场馆规模（默认medium，排除小型LiveHouse）

    返回:
        标准事件 dict 列表，可直接与本项目的 extractor.py 输出合并
    """
    today = datetime.now()

    # 默认时间范围：过去2个月 ~ 未来
    if not start_date:
        start_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    if not end_date:
        # 不设上限，但实际数据不会太远
        end_date = (today + timedelta(days=365 * 2)).strftime("%Y-%m-%d")

    logger.info(
        f"Scraping concerts: {start_date} ~ {end_date}, "
        f"incremental={incremental}, min_venue={min_venue_size}"
    )

    concerts = _scrape_concerts_impl(
        start_date=start_date,
        end_date=end_date,
        incremental=incremental,
        min_venue_size=min_venue_size,
    )

    # 转换为标准事件格式
    translations = _translate_concert_names([c.get("name", "") for c in concerts])
    events = []
    for c in concerts:
        event = _concert_to_event(c, translations.get(c.get("name", ""), ""))
        if event:
            events.append(event)

    logger.info(f"Total concert events: {len(events)}")
    return events


def _concert_to_event(c: Dict, english_name: str = "") -> Optional[Dict]:
    """将爬虫原始数据转换为项目标准事件格式。"""
    name = c.get("name", "").strip()
    venue = c.get("venue", "").strip()
    location = c.get("location", "").strip()
    start_date = c.get("start_date", "")
    end_date = c.get("end_date", "")
    url = c.get("url", "")
    organizer = c.get("organizer", "").strip()

    if not name:
        return None

    # 日期格式转换: YYYY-MM-DD -> YYYY/M/D
    def _fmt_date(d: str) -> str:
        if not d:
            return ""
        try:
            dt = datetime.strptime(d, "%Y-%m-%d")
            return f"{dt.year}/{dt.month}/{dt.day}"
        except ValueError:
            return d

    start_fmt = _fmt_date(start_date)
    end_fmt = _fmt_date(end_date)

    # 场馆规模判断 Priority
    venue_size = _get_venue_size(venue)
    priority = "High" if venue_size == "large" else ""

    # 生成描述
    desc_parts = [f"{name}"]
    if venue:
        desc_parts.append(f"在{venue}举办")
    if start_fmt:
        if end_fmt and end_fmt != start_fmt:
            desc_parts.append(f"演出时间为{start_fmt}至{end_fmt}")
        else:
            desc_parts.append(f"演出时间为{start_fmt}")
    description = "。".join(desc_parts) + "。" if desc_parts else ""

    # 生成标题
    headline = name
    if venue and venue not in name:
        headline = f"{name}（{venue}）"

    # 备注/地点
    remark = venue
    if location and location not in venue:
        remark = f"{location}｜{venue}"

    return {
        "No.": 0,  # 由调用方重新编号
        "事件类型": "文娱活动\nCultural and Entertainment Activities",
        "Link": url,
        "Start Date": start_fmt,
        "End Date": end_fmt,
        "Priority": priority,
        "Event Keywords": name,
        "Event English Keywords": english_name or _fallback_english_title(name),
        "Event Description": description,
        "Headline": headline,
        "备注/地点": remark,
        "来源": organizer,
        "_source": "concert_scraper",
    }


def get_last_scrape_info() -> dict:
    """获取上次采集状态。"""
    state = _load_state()
    return {
        "last_scrape_date": state.get("last_scrape_date", ""),
        "total_scraped_urls": len(state.get("scraped_urls", [])),
    }
