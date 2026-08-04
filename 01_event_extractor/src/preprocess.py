"""
DataFrame preprocessing: column pruning, keyword/city row filtering,
importance ranking, and text conversion for LLM input.
"""
import logging
import os
import re
from io import BytesIO
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Only keep columns useful for LLM extraction
KEY_COLUMNS = {
    "链接", "Link", "帖子链接",
    "发布时间",
    "关键词", "Keywords",
    "账号昵称", "用户昵称",
    "标题", "Headline", "内容", "Content",
    "平台", "平台类型", "来源",
    "作者",
}

# Per-category keyword pre-filters
CATEGORY_PRE_FILTER = {
    "中小学春秋假": ["春假", "秋假", "春秋假", "寒假", "暑假", "寒暑假"],
    "大型会议和展览": ["会议", "展览", "博览会", "峰会", "论坛", "交易会", "服贸会"],
    "体育赛事": ["赛事", "马拉松", "奥运会", "世界杯", "联赛"],
    "文娱活动": ["音乐节", "电影节", "演唱会", "艺术节"],
    "节假日节庆": ["春节", "清明", "五一", "端午", "中秋", "国庆", "放假"],
    "高级别政府会议": ["两会", "人大", "政协", "党代会", "交通管制"],
    "极端天气及自然灾害": ["暴雨", "暴雪", "台风", "地震", "预警", "停运", "航班取消"],
    "进出京政策": ["进京", "出京", "限行", "进京证"],
}

# City whitelists
PROVINCIAL_CAPITALS = {
    "北京", "天津", "上海", "重庆",
    "南京", "杭州", "合肥", "福州", "南昌", "济南",
    "武汉", "长沙", "广州", "成都", "贵阳", "昆明",
    "西安", "兰州", "西宁", "沈阳", "长春", "哈尔滨",
    "郑州", "南宁", "海口", "拉萨", "乌鲁木齐", "呼和浩特",
    "银川", "太原", "石家庄",
}

NEW_TIER1_CITIES = {
    "苏州", "宁波", "无锡", "厦门", "青岛",
    "佛山", "东莞", "深圳", "珠海", "温州",
    "绍兴", "嘉兴", "金华",
}

TARGET_CITIES = PROVINCIAL_CAPITALS | NEW_TIER1_CITIES

PROVINCE_NAMES = {
    "安徽", "四川", "浙江", "江苏", "广东", "湖北", "湖南", "河南",
    "福建", "江西", "山东", "陕西", "云南", "贵州", "甘肃", "青海",
    "辽宁", "吉林", "黑龙江", "广西", "海南", "西藏", "新疆", "内蒙古",
    "宁夏", "山西", "河北",
}

# Max preprocessed text length (chars)
MAX_PREPROCESSED_CHARS = 500_000
# Max content column value length before truncation
MAX_CONTENT_CHARS = 500

# Importance ranking keywords
HIGH_PRIORITY_KEYWORDS = [
    "放假时间", "放假安排", "春假时间", "春假安排", "放假通知",
    "春假日期", "时间确定", "时间公布", "日期确定",
]
LOW_PRIORITY_KEYWORDS = [
    "免费门票", "免票", "半价", "优惠", "消费券", "旅游攻略",
    "研学路线", "旅游推荐", "出行攻略", "热门目的地",
    "一票难求", "免票活动", "门票优惠",
]
NO_CONTENT_KEYWORDS = [
    "新闻早班车", "新闻来了", "早知天下事", "新闻早报", "早安",
]


def preprocess_dataframe(df: pd.DataFrame, mode: str, category: str) -> pd.DataFrame:
    """
    Column pruning + row filtering on a DataFrame.
    1. Keep only KEY_COLUMNS
    2. Filter rows by keywords
    3. For spring_break mode, filter by target cities
    4. Sort by importance (holiday announcements first)
    5. Truncate long content columns
    """
    # Column pruning
    cols_to_keep = [c for c in df.columns if c in KEY_COLUMNS]
    if cols_to_keep:
        df = df[cols_to_keep]

    # Determine filter keywords
    effective_category = category
    if not effective_category and mode == "spring_break":
        effective_category = "中小学春秋假"

    filter_keywords = CATEGORY_PRE_FILTER.get(effective_category, [])
    if not filter_keywords:
        return df

    # Identify columns
    keyword_col = _find_col(df, ["关键词", "Keywords"])
    title_col = _find_col(df, ["标题", "Headline"])
    content_col = _find_col(df, ["内容", "Content"])

    # Build match mask
    mask = pd.Series([False] * len(df), index=df.index)

    for col in [keyword_col, title_col, content_col]:
        if col:
            for kw in filter_keywords:
                mask |= df[col].fillna("").astype(str).str.contains(kw, na=False)

    df = df[mask].reset_index(drop=True)

    # Spring break mode: city filtering
    if mode == "spring_break" or effective_category == "中小学春秋假":
        city_mask = pd.Series([False] * len(df), index=df.index)
        search_cols = [c for c in [title_col, content_col, keyword_col] if c]

        for col in search_cols:
            for city in TARGET_CITIES:
                city_mask |= df[col].fillna("").astype(str).str.contains(city, na=False)
            for prov in PROVINCE_NAMES:
                city_mask |= df[col].fillna("").astype(str).str.contains(
                    prov + r"\d+市", na=False, regex=True
                )
                city_mask |= df[col].fillna("").astype(str).str.contains(
                    prov + "全省", na=False
                )
                city_mask |= df[col].fillna("").astype(str).str.contains(
                    prov + "各市", na=False
                )
                city_mask |= df[col].fillna("").astype(str).str.contains(
                    prov + "全部", na=False
                )

        df = df[city_mask].reset_index(drop=True)

    # Importance sorting for spring break mode
    if mode == "spring_break" or effective_category == "中小学春秋假":
        df = rank_by_importance(df, title_col, content_col, keyword_col)

    # Truncate long content
    if content_col and content_col in df.columns:
        df[content_col] = df[content_col].fillna("").astype(str).apply(
            lambda x: x[:MAX_CONTENT_CHARS] + "..." if len(x) > MAX_CONTENT_CHARS else x
        )

    return df


def rank_by_importance(
    df: pd.DataFrame,
    title_col: Optional[str],
    content_col: Optional[str],
    keyword_col: Optional[str],
) -> pd.DataFrame:
    """Sort rows: holiday announcements > supporting measures > tourism promos > other."""
    search_cols = [c for c in [title_col, content_col, keyword_col] if c]

    scores = []
    for _, row in df.iterrows():
        combined = " ".join(str(row[c]) for c in search_cols if c in row.index)

        score = 0
        for kw in HIGH_PRIORITY_KEYWORDS:
            if kw in combined:
                score += 100
                break

        for city in TARGET_CITIES:
            if city in combined and "春假" in combined:
                score += 50
                break

        for kw in LOW_PRIORITY_KEYWORDS:
            if kw in combined:
                score -= 30
                break

        for kw in NO_CONTENT_KEYWORDS:
            if kw in combined:
                score -= 200
                break

        scores.append(score)

    df = df.copy()
    df["_importance_score"] = scores
    df = df.sort_values("_importance_score", ascending=False).reset_index(drop=True)
    df = df.drop(columns=["_importance_score"])

    return df


def dataframe_to_text(df: pd.DataFrame) -> str:
    """Convert DataFrame to LLM-friendly text format."""
    lines = []
    for idx, row in df.iterrows():
        record_parts = []
        for col in df.columns:
            val = row[col]
            if pd.notna(val) and str(val).strip():
                record_parts.append(f"{col}: {val}")
        if record_parts:
            lines.append(f"--- 记录 {idx + 1} ---")
            lines.append("\n".join(record_parts))
            lines.append("")
    return "\n".join(lines)


def read_and_preprocess_file(path_or_url: str, mode: str, category: str) -> tuple[str, str]:
    """
    Read file, preprocess (column pruning + row filtering), return (text, filename).
    Supports xlsx/xls/csv/txt/json.
    """
    from src.file_utils import read_file_bytes, extract_filename_from_url, infer_extension

    url = path_or_url.strip()
    filename = extract_filename_from_url(url) if url.startswith('http') else os.path.basename(url)
    _, ext = infer_extension(filename)

    try:
        content_bytes, filename, ext = read_file_bytes(url)
    except Exception as e:
        logger.error(f"Failed to read file {url}: {e}")
        return f"[读取文件失败: {str(e)}]", filename

    if ext in (".xlsx", ".xls", ".csv"):
        try:
            stream = BytesIO(content_bytes)
            if ext == ".csv":
                df = pd.read_csv(stream)
            else:
                df = pd.read_excel(stream)

            if df.empty:
                return "[文件为空]", filename

            df = preprocess_dataframe(df, mode, category)

            if df.empty:
                return "[过滤后无相关数据]", filename

            text = dataframe_to_text(df)
            logger.info(f"Preprocessed {filename}: {len(df)} rows, {len(text)} chars")
            return text, filename

        except Exception as e:
            logger.error(f"Failed to parse Excel/CSV {url}: {e}")
            try:
                return content_bytes.decode("utf-8", errors="ignore"), filename
            except Exception:
                return f"[解析文件失败: {str(e)}]", filename

    elif ext == ".json":
        try:
            return content_bytes.decode("utf-8", errors="ignore"), filename
        except Exception as e:
            return f"[解析JSON失败: {str(e)}]", filename

    else:
        try:
            return content_bytes.decode("utf-8", errors="ignore"), filename
        except Exception as e:
            return f"[解析文件失败: {str(e)}]", filename


def pre_filter_raw_text(raw_text: str, mode: str, category: str) -> str:
    """
    Pre-filter raw text: try structured record parsing, fallback to line-level keyword filtering.
    """
    effective_category = category
    if mode == "spring_break":
        effective_category = "中小学春秋假"

    if not raw_text or not raw_text.strip():
        return raw_text

    # Try parsing as structured records
    records = _parse_structured_records(raw_text)
    if records:
        try:
            df = pd.DataFrame(records)
            df = preprocess_dataframe(df, mode, category)
            if not df.empty:
                text = dataframe_to_text(df)
                logger.info(
                    f"Structured raw_text preprocessing: {len(records)} records → "
                    f"{len(df)} rows, {len(text)} chars"
                )
                return text
        except Exception as e:
            logger.warning(f"Structured preprocessing failed: {e}, falling back to line filter")

    # Fallback: line-level keyword filtering
    filter_keywords = CATEGORY_PRE_FILTER.get(effective_category, [])
    if not filter_keywords:
        return raw_text

    lines = raw_text.split("\n")
    matched_indices = set()

    for i, line in enumerate(lines):
        for kw in filter_keywords:
            if kw in line:
                for j in range(max(0, i - 2), min(len(lines), i + 3)):
                    matched_indices.add(j)
                break

    if not matched_indices:
        return raw_text

    filtered_lines = [lines[i] for i in sorted(matched_indices)]
    return "\n".join(filtered_lines)


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    """Find first matching column name from candidates."""
    for name in candidates:
        if name in df.columns:
            return name
    return None


def _parse_structured_records(text: str) -> list[dict]:
    """Try to parse text as structured records."""
    records = []

    if "--- 记录 " in text:
        parts = re.split(r"--- 记录 \d+ ---\n?", text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            record = {}
            for line in part.split("\n"):
                line = line.strip()
                if ": " in line:
                    key, _, val = line.partition(": ")
                    record[key.strip()] = val.strip()
            if record:
                records.append(record)
        return records if records else []

    # Try CSV-like parsing
    lines = text.strip().split("\n")
    if len(lines) >= 2:
        header = lines[0]
        sep = "\t" if "\t" in header else ("," if "," in header else None)
        if sep:
            headers = [h.strip().strip('"') for h in header.split(sep)]
            if len(headers) >= 3:
                for line in lines[1:]:
                    vals = [v.strip().strip('"') for v in line.split(sep)]
                    if len(vals) == len(headers):
                        record = {}
                        for h, v in zip(headers, vals):
                            if v:
                                record[h] = v
                        if record:
                            records.append(record)
                return records if records else []

    return []
