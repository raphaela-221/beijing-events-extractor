# -*- coding: utf-8 -*-
"""Pure dedup-key logic shared by three call sites:

  - 01_event_extractor/src/extractor.py  (extraction-time dedup, all categories)
  - 02_calendar/dedup_canonical_excel.py (Excel-layer dedup on the canonical file)
  - 02_calendar/extract_demo_data.py     (display-layer guard for the calendar)

This is a LEAF module: it imports only `re` so the calendar pipeline can use it
without pulling the openai SDK. Do not add heavy imports here.

Why city-level (not province) keying:
  The old _extract_city_from_headline returned the PROVINCE (成都->四川,
  杭州->浙江). That caused two failure modes --
    (a) miss: when a headline had no recognizable city (e.g. "四川部分高校"),
        the key fell back to the headline string, so two articles about the
        same city got different keys and the dup slipped through;
    (b) false merge: two different cities in the same province with the same
        dates/topic shared a province key and one was wrongly dropped.
  Keying on the CITY fixes both.

Why date-independent for school vacations:
  One city has exactly one 暑假/春假/秋假/寒假 per year. Two articles reporting
  杭州 暑假 with slightly different dates (7/5 vs 7/4) are the SAME event, so
  the vacation key uses city + vacation-type + year, not exact dates.
"""
import re
from typing import Dict, List, Optional, Tuple

# Canonical city names for city-level keying. Covers 直辖市 + 省会 + 新一线 /
# 重点地级市, matching the extractor's TARGET_CITIES whitelist so every in-scope
# event can be keyed to a city.
_CITY_LIST = [
    # 直辖市
    "北京", "上海", "天津", "重庆",
    # 省会
    "南京", "杭州", "合肥", "福州", "南昌", "济南", "武汉", "长沙",
    "广州", "成都", "贵阳", "昆明", "西安", "兰州", "西宁", "沈阳",
    "长春", "哈尔滨", "郑州", "南宁", "海口", "拉萨", "乌鲁木齐",
    "呼和浩特", "银川", "太原", "石家庄",
    # 新一线 / 重点地级市
    "苏州", "宁波", "无锡", "厦门", "青岛", "佛山", "东莞", "深圳",
    "珠海", "温州", "绍兴", "嘉兴", "金华", "大连",
]
# Longest first so e.g. "乌鲁木齐" matches before any partial.
_CITY_LIST_SORTED = sorted(_CITY_LIST, key=len, reverse=True)

# Province names -- used to reject province-as-city in the regex fallback.
_PROVINCE_NAMES = {
    "河北", "山西", "辽宁", "吉林", "黑龙江", "江苏", "浙江", "安徽",
    "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆", "香港", "澳门",
}

_VACATION_RE = re.compile(r"(春假|暑假|秋假|寒假)")


def extract_city(text: str) -> str:
    """Extract a city-level location from free text (headline or keywords).

    Returns the city name, or "" if none. Province-only mentions
    (e.g. "四川部分高校", "浙江各地大中小学") intentionally return "" so the
    caller can fall back to another field.
    """
    if not text:
        return ""
    text = str(text)
    for city in _CITY_LIST_SORTED:
        if city in text:
            return city
    # "XX省YY市" -> YY  (province separates, so greedy match is safe here)
    m = re.search(r"省([一-鿿]{2,3})市", text)
    if m:
        return m.group(1)
    # bare "YY市" at start or after punctuation, but not a province name
    m = re.search(r"(?:^|[，、\s（(])([一-鿿]{2,3})市", text)
    if m and m.group(1) not in _PROVINCE_NAMES:
        return m.group(1)
    return ""


def vacation_type(text: str) -> str:
    """Return 春假/暑假/秋假/寒假 found in text, or ''."""
    if not text:
        return ""
    m = _VACATION_RE.search(str(text))
    return m.group(1) if m else ""


def _g(event: Dict, *names: str):
    """First non-empty value among event[names]. Lets dedup_key work on both
    the Excel schema (Headline/Event Keywords/Topic/Start Date) and the demo
    schema (headline/keywords_zh/topic_zh/start)."""
    for n in names:
        v = event.get(n)
        if v not in (None, ""):
            return v
    return ""


def _topic_zh(event: Dict) -> str:
    topic = str(_g(event, "Topic", "topic_zh", "事件类型"))
    return topic.split("\n", 1)[0].strip()


# Markers that a vacation article is a tourism / multi-region overview
# (family-travel demand, destination rankings) rather than ONE city's official
# break schedule. Such articles mention several regions at once and would
# otherwise collide with -- and delete -- real single-city schedule events.
_TOURISM_MARKERS = (
    "多地", "无缝衔接", "带动", "热度", "亲子游", "加长版",
    "上榜", "热门目的地", "预订", "出行热度", "出游",
)


def _is_vacation_overview(kw: str, headline: str) -> bool:
    """True if this looks like a multi-region/tourism overview, not a single
    city's break schedule."""
    text = f"{kw} {headline}"
    if any(m in text for m in _TOURISM_MARKERS):
        return True
    # 2+ province names in keywords => multi-region overview
    provs = [p for p in _PROVINCE_NAMES if p in kw]
    if len(provs) >= 2:
        return True
    return False


def _norm_hl(s: str) -> str:
    """Normalize a headline for exact-match keying: strip + collapse whitespace.
    So trailing-space variants (e.g. '...赛跑活动 ' vs '...赛跑活动') don't
    defeat same-headline detection."""
    return re.sub(r"\s+", " ", str(s).strip())


def dedup_key(event: Dict) -> str:
    """Stable dedup key for an event.

    - 中小学假期 / 中小学春秋假 / 中小学寒暑假: city + vacation-type + year (date-independent).
      (中小学假期 是 extract 层把 春秋假/寒暑假 合并后的大 topic；原始两值来自 canonical Excel。)
    - other categories: city + start + end + topic.
    - no city extractable: fall back to headline + date(s).
    """
    topic_zh = _topic_zh(event)
    headline = str(_g(event, "Headline", "headline")).strip()
    start = str(_g(event, "Start Date", "start")).strip()[:10]
    end = str(_g(event, "End Date", "end")).strip()[:10]
    kw = str(_g(event, "Event Keywords", "keywords_zh"))

    if topic_zh in ("中小学春秋假", "中小学寒暑假", "中小学假期"):
        vtype = vacation_type(kw) or vacation_type(headline)
        year = start[:4] if start else ""
        # Tourism / multi-region overview articles (e.g. "昆明上榜热门目的地"
        # whose keywords list 沈阳/山东/湖南/浙江 多地春假 driving family-travel
        # demand) are NOT a single city's break schedule. Key them by headline
        # so they neither collide with nor delete real schedule events.
        if _is_vacation_overview(kw, headline):
            return f"vac|overview|{headline}|{vtype}|{year}"
        # Prefer the city from KEYWORDS (the schedule field: city + 学段 +
        # dates), not the headline, which can name a city as a destination.
        city = extract_city(kw) or extract_city(headline)
        if city:
            return f"vac|{city}|{vtype}|{year}"
        return f"vac|HL|{headline}|{vtype}|{year}"

    # Non-vacation categories: same headline + same dates = same event (dedup).
    # Same headline but DIFFERENT dates = different days (keep, e.g. recurring
    # CBA rounds). Same date but DIFFERENT headline = different events (keep,
    # e.g. 亦庄马拉松 vs 通州马拉松, both 北京 on 4/19). So key on headline +
    # dates + topic, NOT city + dates + topic (which would wrongly merge
    # same-city same-day different events).
    return f"{_norm_hl(headline)}|{start}|{end}|{topic_zh}"


def _keep_score(event: Dict) -> int:
    """Higher = preferred to keep within a duplicate group.

    Prefers: city_activity_list source (authoritative) > headline that names a
    city (specific) > keywords with an explicit day count > non-rollup headline.
    """
    score = 0
    if str(_g(event, "_source")) == "city_activity_list":
        score += 10
    headline = str(_g(event, "Headline", "headline"))
    kw = str(_g(event, "Event Keywords", "keywords_zh"))
    if extract_city(headline):
        score += 2
    if "共" in kw and "天" in kw:
        score += 1
    elif re.search(r"\d+\s*天", kw):
        score += 1
    if "各地" not in headline and "多市" not in headline and "全省" not in headline:
        score += 1
    return score


def _has_identity(event: Dict) -> bool:
    """An event needs at least a headline, a topic, or a start date to have an
    identity worth deduping on. Rows with only a Link (and nothing else) are
    malformed extraction leftovers -- pass them through untouched."""
    return bool(
        _g(event, "Headline", "headline")
        or _g(event, "Topic", "topic_zh", "事件类型")
        or _g(event, "Start Date", "start")
    )


def deduplicate_events(
    events: List[Dict],
    only_categories: Optional[List[str]] = None,
) -> Tuple[List[Dict], List[Dict]]:
    """Deduplicate events by dedup_key, keeping the highest-scoring per group.

    Args:
        events: list of event dicts (any schema understood by dedup_key/_g).
        only_categories: if set, only events whose topic_zh is in this set are
            subject to dedup; all others pass through untouched. None = dedup
            all categories (used by the extraction flow).

    Returns (kept, removed), each in original relative order.
    """
    only = set(only_categories) if only_categories else None

    groups: Dict[str, List[Tuple[int, Dict]]] = {}
    passthrough: List[Tuple[int, Dict]] = []
    for i, ev in enumerate(events):
        if not _has_identity(ev):
            passthrough.append((i, ev))
            continue
        if only is not None and _topic_zh(ev) not in only:
            passthrough.append((i, ev))
            continue
        k = dedup_key(ev)
        groups.setdefault(k, []).append((i, ev))

    kept: List[Tuple[int, Dict]] = []
    removed: List[Tuple[int, Dict]] = []
    for items in groups.values():
        if len(items) == 1:
            kept.append(items[0])
            continue
        # highest score wins; tie -> earliest original index
        best = max(range(len(items)), key=lambda j: (_keep_score(items[j][1]), -items[j][0]))
        kept.append(items[best])
        for j, it in enumerate(items):
            if j != best:
                removed.append(it)

    kept = kept + passthrough
    kept.sort(key=lambda t: t[0])
    removed.sort(key=lambda t: t[0])
    return [e for _, e in kept], [e for _, e in removed]


def group_duplicates(
    events: List[Dict],
) -> List[Tuple[str, List[Dict]]]:
    """Report-only: return (key, [events]) for every key shared by >1 event,
    in first-seen order. Used by the Excel script to flag non-vacation dups
    without removing them."""
    groups: Dict[str, List[Dict]] = {}
    order: List[str] = []
    for ev in events:
        if not _has_identity(ev):
            continue
        k = dedup_key(ev)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(ev)
    return [(k, groups[k]) for k in order if len(groups[k]) > 1]
