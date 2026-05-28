"""
Smart information extractor: uses LLM to extract structured event data from raw documents.
Rewritten to use openai SDK instead of Coze's LLMClient.
Supports two modes: 中小学春秋假 / 事件总结 (8 categories).
"""
import json
import logging
import os
import re
import traceback
from typing import List, Dict, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

# ============================================================
# 8 event categories with Chinese/English names
# ============================================================
CATEGORIES = {
    "大型会议和展览": "Significant Conferences and Exhibitions",
    "体育赛事": "Sports Events",
    "文娱活动": "Cultural and Entertainment Activities",
    "节假日节庆": "Holiday Celebrations",
    "高级别政府会议": "High-profile Government Meetings",
    "极端天气及自然灾害": "Extreme Weather & Natural Disasters",
    "中小学春秋假": "Spring and Autumn Breaks",
    "进出京政策": "Entry and Exit Beijing Policies",
}

# Filename keyword → category mapping
_FILENAME_CATEGORY_MAP = {
    "大型会议": "大型会议和展览",
    "展览": "大型会议和展览",
    "会议和展览": "大型会议和展览",
    "体育赛事": "体育赛事",
    "体育": "体育赛事",
    "赛事": "体育赛事",
    "文娱活动": "文娱活动",
    "文娱": "文娱活动",
    "娱乐": "文娱活动",
    "节假日": "节假日节庆",
    "节庆": "节假日节庆",
    "节日": "节假日节庆",
    "政府会议": "高级别政府会议",
    "政务": "高级别政府会议",
    "高级别": "高级别政府会议",
    "极端天气": "极端天气及自然灾害",
    "自然灾害": "极端天气及自然灾害",
    "灾害": "极端天气及自然灾害",
    "天气": "极端天气及自然灾害",
    "春秋假": "中小学春秋假",
    "春假": "中小学春秋假",
    "秋假": "中小学春秋假",
    "寒暑假": "中小学春秋假",
    "寒假": "中小学春秋假",
    "暑假": "中小学春秋假",
    "进出京": "进出京政策",
    "进京": "进出京政策",
    "出京": "进出京政策",
    "城市活动事件列表": "城市活动事件列表",
}

# ============================================================
# City whitelists
# ============================================================
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

PROVINCE_TO_CAPITAL = {
    "安徽": "合肥", "四川": "成都", "浙江": "杭州", "江苏": "南京",
    "广东": "广州", "湖北": "武汉", "湖南": "长沙", "河南": "郑州",
    "福建": "福州", "江西": "南昌", "山东": "济南", "陕西": "西安",
    "云南": "昆明", "贵州": "贵阳", "甘肃": "兰州", "青海": "西宁",
    "辽宁": "沈阳", "吉林": "长春", "黑龙江": "哈尔滨",
    "广西": "南宁", "海南": "海口", "西藏": "拉萨",
    "新疆": "乌鲁木齐", "内蒙古": "呼和浩特", "宁夏": "银川",
    "山西": "太原", "河北": "石家庄", "北京": "北京",
    "天津": "天津", "上海": "上海", "重庆": "重庆",
}

# ============================================================
# Base system prompt for extraction
# ============================================================
_BASE_SYSTEM_PROMPT = """# 角色定义
你是一个专业的信息提取助手，擅长从新闻/帖子类原始文档中精准提取结构化事件数据。

# 任务目标
从用户提供的原始文档内容中，提取所有与指定事件类型相关的核心事件，输出为 JSON 数组。
原始数据为社交媒体帖子/新闻报道，每条记录包含平台、标题、内容、发布时间、帖子链接等字段。
同一事件可能有多篇相似报道，需要合并为一条事件记录。

# 通用提取规则
1. **去重合并**：同一事件有多篇相似报道时，合并为一条事件记录。权威性排序：官方政府账号 > 主流媒体（新华网、人民日报、央视新闻等） > 地方媒体 > 自媒体。Link 取最权威来源的链接
2. **排序规则**：High Priority 事件排在前面，非 High 事件排在后面；同级别内按时间排序
3. **完整性**：每个事件必须包含所有字段
4. **日期格式**：统一为 yyyy/m/d（如2026/4/1），无前导零
5. **日期必填**：Start Date 和 End Date **不得为空**，必须根据文章内容填写具体日期。如果文章未明确日期，根据上下文合理推断

# 字段说明
每个事件包含以下字段：
- "No.": 序号（从1开始）
- "事件类型": 事件类型名称，格式为"中文名称\\n英文名称"（如"大型会议和展览\\nSignificant Conferences and Exhibitions"）
- "Link": 原文链接URL（取最权威来源，必须保留完整URL不可截断）
- "Start Date": 事件开始日期，格式为 yyyy/m/d，**必填**
- "End Date": 事件结束日期，格式同上，**必填**；如春假与法定节假日（如清明、五一）连休，End Date 应填连休窗口的最后一天
- "Priority": 重要性判定，详见各分类规则
- "Event Keywords": 根据事件类型按要求填写（春假类写完整描述，会议/赛事/文娱只写名称，其他简洁描述），详见下方各分类规则，**不是**逗号分隔标签列表
- "Event English Keywords": 英文完整描述性短语，将中文关键词短语翻译为流利英文
- "Event Description": 中文详细描述，2-4句话，80-200字
- "Headline": 中文标题（直接使用原文标题）
- "备注/地点": 补充说明。春假场景填写Priority判定理由（如"省会城市+连休≥6天→High"或"非省会+连休<6天"）；通用事件场景填写事件地点
- "来源": 文章发布者的账号名称或媒体名称（如"北京发布""成都发布""人民日报""央视新闻"等），从文章标题、公众号名称或内容中提取

# 输出格式
严格输出 JSON 数组，不要包含任何其他文字说明或 markdown 标记。"""

# ============================================================
# Per-category extraction prompts
# ============================================================
CATEGORY_PROMPTS = {
    "中小学春秋假": """
# 本分类专属规则

## 事件类型名称
"中小学春秋假\\nSpring and Autumn Breaks"

## 核心原则：重点提取放假时间公告
本提取任务的**核心目标**是提取各省市中小学寒暑假/春假/秋假的**放假时间安排**。
文档内容可能是关于寒假、暑假、春假或秋假的，请根据文档实际主题提取对应类型的放假时间。
文旅促销、景区优惠、交通运力等配套信息属于次要内容，提取时Priority不得标High。

## 筛选标准
提取以下两类信息：
1. **放假时间公告（核心）**：各省市正式发布的寒暑假/春假/秋假放假时间、实施范围、连休安排
2. **配套措施（次要）**：与放假直接相关的配套政策（如公益托管、弹性休假等）

以下类型的文章**必须排除**，不要提取：
- 政策提案、建议、政府工作报告提及但未正式实施（如"建议设置""拟推行""首次写入报告""研究探索"等措辞）
- 仅有"待定""具体时间另行通知"等无明确日期的公告
- 纯旅游推广或营销内容，与放假安排无关
- 同一城市同一放假安排的重复报道（仅保留最权威来源的一篇）
- 纯文旅促销（景区免票/优惠、旅游消费券、研学路线推荐、旅游攻略等），不包含任何放假时间信息
- 纯交通运力信息（铁路加开、航班增加等），不包含任何放假时间信息
- 改革试点/入选典型项目等新闻，不包含具体放假时间

## 城市过滤
仅保留以下目标城市的相关文章：
- 省会城市：北京、天津、上海、重庆、南京、杭州、合肥、福州、南昌、济南、武汉、长沙、广州、成都、贵阳、昆明、西安、兰州、西宁、沈阳、长春、哈尔滨、郑州、南宁、海口、拉萨、乌鲁木齐、呼和浩特、银川、太原、石家庄
- 新一线城市：苏州、宁波、无锡、厦门、青岛、佛山、东莞、深圳、珠海、温州、绍兴、嘉兴、金华
- 如果一篇文章覆盖整个省份（如"安徽16市""四川21市州""贵州9市州"），应保留，并用该省省会城市作为代表
- 地级市/县级市（不在上述名单中）应排除，除非文章覆盖整个省份

## Priority 判定（严格）
**只有放假时间公告类事件才可能标High，配套措施/文旅促销一律不标High！**

放假时间公告事件的Priority判定：
- **High**：该城市为省会城市 且 文章包含明确的放假时间安排
- **High**：连休窗口总天数 ≥ 6天（假期本身 + 相连的法定假日/周末）
- 空字符串：非省会城市且连休窗口 < 6天

**以下情况Priority必须为空字符串**：
- 文旅促销/景区优惠/免票活动（无论城市是否为省会）
- 交通运力保障/出行热度信息
- 公益托管/弹性休假等配套措施
- 研学路线/旅游攻略/消费券发放
- 试点改革/入选典型项目等政策新闻（无具体放假时间）

## Start Date 和 End Date 规则（强制）
**每个事件必须有Start Date和End Date，不得为空！**
- Start Date：放假开始日期
- End Date：连休窗口的最后一天（如果假期与法定节假日/周末连休，End Date应填连休窗口的最后一天）
- 例如：春假4月1-3日 + 清明节4月4-6日 → Start Date=2026/4/1, End Date=2026/4/6
- 例如：寒假1月18日-2月16日 → Start Date=2026/1/18, End Date=2026/2/16
- 如果是文旅促销等配套事件，Start Date和End Date填写活动/优惠的起止日期
- 如果文章未明确具体日期，根据上下文合理推断（如"4月1日开始放春假"→ Start Date=2026/4/1）

## Event Keywords 格式
必须写成**完整的描述性短语**，包含城市、学段、日期、连休信息，例如：
- "安徽省合肥市义务教育阶段一至八年级春假4月1日至3日 与清明节假期连休共6天"
- "辽宁省沈阳市义务教育阶段春假4月28日至30日 与五一假期连休"
- "北京市中小学寒假1月18日至2月16日 共30天"
**不要**写成逗号分隔的关键词列表（如"合肥,春假,4月1日"）
文旅促销类事件的Keywords应明确标注其性质，如：
- "浙江省推出春假文旅优惠 超100家景区面向中小学生免费或半价"

## 排序规则
1. 放假时间公告事件排在前面，按省会城市优先、日期先后排序
2. 配套措施/文旅促销事件排在后面

## 备注字段规则（放假时间场景）
- Priority为High的事件：备注填写判定理由，如"省会城市+连休≥6天→High"
- Priority为空的事件：备注填写原因，如"非省会+连休<6天"或"文旅促销/配套措施"
- 如果有特殊上下文需要补充，也可在此字段说明

## 来源字段规则
- 填写文章发布者的账号名称（如"安徽发布""成都发布""杭州发布"等）
- 从文章标题、公众号名称或内容中识别提取
- 如果来源不明确，填写媒体平台名称（如"微信公众号"）
""",

    "大型会议和展览": """
# 本分类专属规则

## 事件类型名称
"大型会议和展览\\nSignificant Conferences and Exhibutions"

## 筛选标准
- **仅提取参与人数大于10,000人的活动，或国际级/国家级重要会议和展览**
- 地方性/行业性小型活动（参与人数<10,000且非国际国家级）不提取
- 无法判断人数时，需根据会议/展览名称和内容评估其级别

## Priority 判定
- **High**：参与人数明确>10,000人的活动
- **High**：无法判断人数，但为国际知名展会/会议（如广交会、博鳌论坛、达沃斯论坛、进博会等）
- **High**：国家级重要会议/展览（如全国两会相关、中国国际工业博览会等）
- 空字符串：其他符合筛选标准但非国际/国家级的活动

## Event Keywords 格式
只保留**事件名称**即可，例如：
- "中国发展高层论坛2026年年会"
- "2026中关村论坛年会"
- "第十四届储能国际峰会暨展览会"
**不要**写成完整描述性段落或逗号分隔的关键词列表。

## 识别提示
- 关注会议/展览的规模描述（如"数万""10万""大规模"等）
- 关注举办场馆（国家会议中心、新国展、上交会等大型场馆通常容纳万人以上）
- 关注主办方级别（国家级部委主办通常规模较大）
""",

    "体育赛事": """
# 本分类专属规则

## 事件类型名称
"体育赛事\\nSports Events"

## 筛选标准
- **仅提取参与人数大于10,000人的赛事，或国际级/国家级重要体育赛事**
- 地方性/群众性小型赛事（参与人数<10,000且非国际国家级）不提取
- 无法判断人数时，需根据赛事名称和级别评估

## Priority 判定
- **High**：参与人数明确>10,000人的赛事
- **High**：国际知名赛事（如奥运会、世界杯、亚运会、F1、NBA中国赛等）
- **High**：国家级重大赛事（如全运会、中超联赛、CBA全明星等）
- 空字符串：其他符合筛选标准但非国际/国家级的赛事

## Event Keywords 格式
只保留**赛事名称**即可，例如：
- "2026北京马拉松"
- "中超联赛第5轮"
- "F1中国大奖赛"
**不要**写成完整描述性段落或逗号分隔的关键词列表。

## 识别提示
- 关注赛事的场馆容量和上座率描述
- 关注赛事级别（国际级/国家级/省级/市级）
- 马拉松等大规模群众赛事通常参与人数过万
""",

    "文娱活动": """
# 本分类专属规则

## 事件类型名称
"文娱活动\\nCultural and Entertainment Activities"

## 筛选标准
- **仅提取参与人数大于10,000人的活动，或国际级/国家级大型文娱活动**
- 小型演出、地方性文化活动（参与人数<10,000且非国际国家级）不提取
- 无法判断人数时，需根据活动名称、场馆和级别评估

## Priority 判定
- **High**：参与人数明确>10,000人的活动
- **High**：国际知名演出/音乐节（如格莱美相关活动、国际音乐节等）
- **High**：国家级大型文娱活动（如春晚相关、央视大型晚会等）
- 空字符串：其他符合筛选标准但非国际/国家级的活动

## Event Keywords 格式
只保留**活动名称**即可，例如：
- "第十六届北京国际电影节"
- "2026草莓音乐节"
- "周杰伦演唱会北京站"
**不要**写成完整描述性段落或逗号分隔的关键词列表。

## 识别提示
- 关注演出场馆（鸟巢、工体、五棵松等大型场馆通常容纳万人以上）
- 音乐节、跨年晚会等大型活动通常参与人数过万
- 关注票务信息中的座位数/容量描述
""",

    "节假日节庆": """
# 本分类专属规则

## 事件类型名称
"节假日节庆\\nHoliday Celebrations"

## 筛选标准
- 提取与节假日/节庆相关的重大活动、习俗、各地庆典
- 关注法定节假日的放假安排、调休政策
- 关注各地特色节庆活动

## Priority 判定
- **High**：法定节假日（春节、清明、五一、端午、中秋、国庆等）
- **High**：全国性重大节庆活动
- 空字符串：地方性节庆活动、非法定假日

## Event Keywords 格式
简洁表明事件即可，例如：
- "2026年清明节放假安排 4月4日至6日"
- "北京玉渊潭樱花节"
- "广西壮族三月三"
**不要**写成完整描述性段落或逗号分隔的关键词列表。

## 识别提示
- 法定节假日日期和调休安排为高优先级
- 各地举办的赏花节、文化节等地方性活动视规模判断
""",

    "高级别政府会议": """
# 本分类专属规则

## 事件类型名称
"高级别政府会议\\nHigh-profile Government Meetings"

## 筛选标准
- **仅提取可能影响进出京交通的高级别政府会议/政务活动**
- 普通政府工作会议、专题研讨会、不影响交通的会议不提取
- 核心判断依据：会议是否会导致交通管制、道路封闭、公交甩站、地铁封闭等影响进出京的措施

## Priority 判定
- **High**：全国两会（全国人大、全国政协会议）
- **High**：党代会（中国共产党全国代表大会）
- **High**：国事访问、阅兵、一带一路高峰论坛等最高级别外事活动
- **High**：在人民大会堂、钓鱼台、国家会议中心、长安街沿线等核心区域举办并导致交通管制的会议
- **High**：明确提及交通管制、临时交通管理、道路封闭、公交甩站、地铁封闭等措施的会议
- 空字符串：级别较高但不影响进出京交通的会议

## Event Keywords 格式
简洁表明事件即可，例如：
- "十四届全国人大四次会议代表建议交办会"
- "第二届中国消费市场博览会"
- "2026全球数字经济大会"
**不要**写成完整描述性段落或逗号分隔的关键词列表。

## 识别提示
- 关注会议举办地点：人民大会堂、钓鱼台、国家会议中心、天安门、长安街沿线
- 关注交通管制关键词：交通管制、临时交通管理、道路封闭、禁止通行、公交甩站、地铁封闭
- 关注官方信息来源：北京交管局、@北京交警、北京本地宝
- 不影响交通的部级/司局级会议不应提取
""",

    "极端天气及自然灾害": """
# 本分类专属规则

## 事件类型名称
"极端天气及自然灾害\\nExtreme Weather & Natural Disasters"

## 筛选标准
- 提取所有影响出行/交通的极端天气事件和自然灾害
- 包括但不限于：台风、暴雨、暴雪、大雾、沙尘暴、高温、寒潮、洪水、地震、地质灾害等
- 关注对交通、出行、旅游有实际影响的事件

## Priority 判定
- **High**：重大灾害（造成人员伤亡、大范围交通中断）
- **High**：红色预警信号
- **High**：大范围影响（多省/多市受灾）
- **High**：导致航班大面积取消、高铁停运、高速封闭的事件
- 空字符串：局部影响、普通预警（蓝/黄色）、未造成实质交通影响

## Event Keywords 格式
简洁表明事件即可，例如：
- "2026年4月华北地区沙尘暴 导致航班大面积取消"
- "台风'银杏'登陆华南 多条高铁线路停运"
- "京津冀地区暴雨红色预警"
**不要**写成完整描述性段落或逗号分隔的关键词列表。

## 识别提示
- 关注预警级别（蓝色/黄色/橙色/红色）
- 关注影响范围和交通中断情况
- 关注官方气象部门发布的预警信息
""",

    "进出京政策": """
# 本分类专属规则

## 事件类型名称
"进出京政策\\nEntry and Exit Beijing Policies"

## 筛选标准
- 提取所有与进出北京相关的政策调整、限制措施、通行规定
- 包括但不限于：限行政策、进京证政策、交通管控、安检升级等
- 关注政策变化对出行客流的影响

## Priority 判定
- **High**：重大政策调整（如新增限行、进京政策收紧/放宽）
- **High**：影响大范围人群的通行措施
- 空字符串：常规性/延续性政策、局部小幅调整

## 识别提示
- 关注政策生效时间和适用范围
- 关注进京证办理要求变化
- 关注限行区域和时段调整
""",
}


def get_llm_client() -> OpenAI:
    """Create an OpenAI client configured from environment variables."""
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY not set. Please set it in .env file or environment variable."
        )

    import httpx
    bypass_proxy = os.getenv("OPENAI_BYPASS_PROXY", "1") == "1"
    http_client = httpx.Client(
        timeout=300.0,
        trust_env=not bypass_proxy,
    )

    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        http_client=http_client,
    )


def guess_category_from_filename(file_name: str) -> Optional[str]:
    """Infer event category from filename."""
    from urllib.parse import unquote

    name = os.path.splitext(os.path.basename(file_name))[0]

    try:
        decoded_name = unquote(name)
    except Exception:
        decoded_name = name

    search_text = name + decoded_name

    sorted_keywords = sorted(_FILENAME_CATEGORY_MAP.keys(), key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in search_text:
            return _FILENAME_CATEGORY_MAP[keyword]

    return None


def get_category_type_name(category: str) -> str:
    """Get combined Chinese/English category name."""
    en_name = CATEGORIES.get(category, "")
    if en_name:
        return f"{category}\\n{en_name}"
    return category


def build_system_prompt(category: str) -> str:
    """Build full system prompt for a category."""
    base = _BASE_SYSTEM_PROMPT
    category_prompt = CATEGORY_PROMPTS.get(category, "")
    type_name_note = f'\n\n# 当前提取的事件类型\n事件类型固定为："{get_category_type_name(category)}"'

    return base + category_prompt + type_name_note


def _filter_events_by_city(events: List[Dict]) -> List[Dict]:
    """Filter spring break events by city whitelist."""
    filtered = []
    for event in events:
        text_to_check = " ".join([
            str(event.get("Headline", "")),
            str(event.get("Event Keywords", "")),
            str(event.get("Event Description", "")),
            str(event.get("备注/地点", "") or event.get("备注", "")),
        ])

        is_province_level = False
        for province, capital in PROVINCE_TO_CAPITAL.items():
            if province in text_to_check:
                province_patterns = [
                    f"{province}.*全省", f"{province}\\d+市", f"{province}\\d+市州",
                    f"{province}全部", f"{province}各地", f"{province}各市",
                ]
                for pat in province_patterns:
                    if re.search(pat, text_to_check):
                        is_province_level = True
                        event["_representative_city"] = capital
                        break
            if is_province_level:
                break

        if is_province_level:
            filtered.append(event)
            continue

        city_found = False
        for city in TARGET_CITIES:
            if city in text_to_check:
                city_found = True
                break

        if city_found:
            filtered.append(event)
        else:
            logger.info(f"Filtered out event (city not in whitelist): {str(event.get('Headline', ''))[:60]}")

    return filtered


def extract_events(
    raw_text: str,
    mode: str = "auto",
    category: str = "中小学春秋假",
    topic: str = "",
    model: str = "",
    extra_info: str = "",
) -> List[Dict]:
    """
    Extract structured event data from raw text using LLM.
    Auto-chunks long text to avoid context window limits.
    """
    if mode == "spring_break":
        effective_category = "中小学春秋假"
    else:
        effective_category = category or "中小学春秋假"

    model = model or os.getenv("OPENAI_MODEL", "deepseek-v4-flash")

    _CHUNK_SIZE = 25_000
    _CHUNK_OVERLAP = 2_000

    text_len = len(raw_text)

    if text_len <= _CHUNK_SIZE:
        events = _extract_events_single(
            raw_text=raw_text,
            effective_category=effective_category,
            topic=topic,
            model=model,
            extra_info=extra_info,
        )
    else:
        num_chunks = max(1, (text_len + _CHUNK_SIZE - 1) // _CHUNK_SIZE)
        logger.info(
            f"Text length {text_len} chars exceeds chunk size {_CHUNK_SIZE}, "
            f"splitting into ~{num_chunks} chunks"
        )

        chunks = []
        start = 0
        while start < text_len:
            end = min(start + _CHUNK_SIZE, text_len)
            chunks.append(raw_text[start:end])
            start = end - _CHUNK_OVERLAP if end < text_len else end

        all_events = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i + 1}/{len(chunks)}, size={len(chunk)} chars")
            try:
                chunk_events = _extract_events_single(
                    raw_text=chunk,
                    effective_category=effective_category,
                    topic=topic,
                    model=model,
                    extra_info=extra_info,
                )
                all_events.extend(chunk_events)
            except Exception as e:
                logger.warning(f"Chunk {i + 1} extraction failed: {e}")
                continue

        events = _deduplicate_events(all_events)

    # Post-processing
    events = _postprocess_events(events, effective_category)

    # City whitelist filter for spring break
    if mode == "spring_break" or effective_category == "中小学春秋假":
        events = _filter_events_by_city(events)
        for idx, event in enumerate(events, 1):
            event["No."] = idx

    logger.info(f"Total extracted {len(events)} events for category={effective_category}")
    return events


def _extract_events_single(
    raw_text: str,
    effective_category: str,
    topic: str = "",
    model: str = "deepseek-v4-flash",
    extra_info: str = "",
) -> List[Dict]:
    """Single LLM call for event extraction."""
    client = get_llm_client()

    system_prompt = build_system_prompt(effective_category)

    topic_desc = topic or effective_category

    _KEYWORDS_RULES = {
        "中小学春秋假": "Event Keywords 用一句话清楚表述放假城市和时间（如'杭州市3月27-31日春假，连休5天'）",
        "大型会议和展览": "Event Keywords 只保留事件名称即可（如'中国发展高层论坛2026年年会'）",
        "体育赛事": "Event Keywords 只保留赛事名称即可（如'2026北京马拉松'）",
        "文娱活动": "Event Keywords 只保留活动名称即可（如'第十六届北京国际电影节'）",
        "节假日节庆": "Event Keywords 简洁表明事件即可（如'2026年清明节放假安排 4月4日至6日'）",
        "高级别政府会议": "Event Keywords 简洁表明事件即可（如'十四届全国人大四次会议代表建议交办会'）",
        "极端天气及自然灾害": "Event Keywords 简洁表明事件即可（如'京津冀地区暴雨红色预警'）",
        "进出京政策": "Event Keywords 简洁表明事件即可",
    }
    keywords_rule = _KEYWORDS_RULES.get(effective_category, "Event Keywords 简洁表明事件即可")

    user_parts = [
        f"请从以下原始文档内容中，提取所有与「{topic_desc}」相关的核心事件。",
        "",
        "要求：",
        "1. 严格按照上述规则筛选和排序",
        "2. 日期格式为 yyyy/m/d（如2026/4/1，无前导零）",
        f"3. {keywords_rule}，不要写成逗号分隔的关键词列表",
        "4. 严格输出 JSON 数组，不要包含任何其他文字",
    ]

    if extra_info.strip():
        user_parts.append(f"5. 用户补充要求：{extra_info.strip()}")

    user_parts.extend([
        "",
        "--- 原始文档内容 ---",
        raw_text,
        "--- 文档结束 ---",
    ])

    user_message = "\n".join(user_parts)

    logger.info(f"Calling LLM: category={effective_category}, model={model}, text_len={len(raw_text)}")

    estimated_tokens = len(raw_text) * 1.5
    if estimated_tokens > 250_000:
        logger.warning(
            f"Text length {len(raw_text)} chars (~{estimated_tokens:.0f} tokens) "
            f"may exceed model context limit."
        )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_completion_tokens=32768,
        )

        content = response.choices[0].message.content or ""
        content = content.strip()

        return _parse_json_response(content)

    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error (attempt 1): {e}\nContent preview: {content[:300]}")

        # Retry with correction prompt
        try:
            retry_response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "你上次输出的 JSON 格式有误，请修正后重新输出。要求：1) 严格输出合法 JSON 数组；2) 所有字符串值中的引号必须转义为 \\\"；3) 不要包含任何 JSON 之外的文字。"},
                ],
                temperature=0.1,
                max_completion_tokens=32768,
            )

            retry_content = retry_response.choices[0].message.content or ""
            retry_content = retry_content.strip()

            return _parse_json_response(retry_content)

        except Exception as retry_err:
            logger.error(f"Retry also failed: {retry_err}")
            raise ValueError(f"LLM output could not be parsed as JSON: {str(e)}")
    except Exception as e:
        logger.error(f"Extraction failed: {traceback.format_exc()}")
        raise


def _parse_json_response(content: str) -> List[Dict]:
    """Parse LLM response content as JSON array."""
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()

    json_str = content.strip()
    if not json_str.startswith("["):
        bracket_start = json_str.find("[")
        bracket_end = json_str.rfind("]")
        if bracket_start >= 0 and bracket_end > bracket_start:
            json_str = json_str[bracket_start:bracket_end + 1]

    events = json.loads(json_str)

    if not isinstance(events, list):
        raise ValueError(f"LLM returned non-array JSON: {type(events)}")

    logger.info(f"Single chunk extracted {len(events)} events")
    return events


def _normalize_city(name: str) -> str:
    """Normalize city/province name for fuzzy matching."""
    if not name:
        return ""
    n = re.sub(r"(省|市|自治区|壮族自治区|维吾尔|回族|藏族|特别行政区)$", "", name.strip())
    n = n.replace(" ", "")
    return n


_CITY_ALIASES = {
    "内蒙": "内蒙古", "呼和浩特": "内蒙古",
    "银川": "宁夏",
    "拉萨": "西藏",
    "南宁": "广西",
    "乌鲁木齐": "新疆",
    "长春": "吉林", "吉林市": "吉林",
    "哈尔滨": "黑龙江",
    "沈阳": "辽宁", "大连": "辽宁",
    "石家庄": "河北",
    "济南": "山东", "青岛": "山东",
    "郑州": "河南",
    "武汉": "湖北",
    "长沙": "湖南",
    "南昌": "江西",
    "合肥": "安徽",
    "南京": "江苏",
    "杭州": "浙江",
    "福州": "福建",
    "广州": "广东", "深圳": "广东",
    "海口": "海南",
    "成都": "四川", "重庆": "重庆",
    "贵阳": "贵州",
    "昆明": "云南",
    "西安": "陕西",
    "兰州": "甘肃",
    "西宁": "青海",
    "太原": "山西",
    "北京": "北京",
    "上海": "上海",
    "天津": "天津",
}


def _extract_city_from_headline(headline: str) -> str:
    """Extract city/province name from Headline."""
    if not headline:
        return ""
    for city, region in _CITY_ALIASES.items():
        if city in headline:
            return region
    m = re.search(r"([一-鿿]{2,4})(省|市|自治区)", headline)
    if m:
        return _normalize_city(m.group(0))
    return ""


def extract_from_city_activity_list(
    url_or_path: str,
    category: str = "城市活动事件列表",
) -> List[Dict]:
    """
    Read and filter events from a structured city activity event list (Excel).
    Priority=High events are kept; empty Priority events are filtered by LLM.
    """
    import pandas as pd
    from src.file_utils import read_file_bytes, extract_filename_from_url

    # Download/read file
    file_path = None
    if os.path.exists(url_or_path):
        file_path = url_or_path
    elif url_or_path.startswith("http"):
        try:
            content_bytes, _, ext = read_file_bytes(url_or_path)
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp.write(content_bytes)
            tmp.close()
            file_path = tmp.name
        except Exception as e:
            logger.warning(f"[城市活动列表] 下载文件失败: {e}")
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"[城市活动列表] 无法获取文件: {url_or_path}")
        return []

    # Read Excel
    try:
        if file_path.lower().endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
    except Exception as e:
        logger.warning(f"[城市活动列表] 读取文件失败: {e}")
        return []

    if df.empty:
        logger.warning("[城市活动列表] 文件为空")
        return []

    # Standardize column names
    df.columns = [str(c).strip() for c in df.columns]
    col_map = {c.lower().replace(' ', ''): c for c in df.columns}

    # Find key columns
    priority_col = _find_col_from_map(col_map, ['priority', '优先级', 'prioritylevel'])
    headline_col = _find_col_from_map(col_map, ['headline', '事件名称', 'eventname', 'title', '名称'])
    desc_col = _find_col_from_map(col_map, ['description', '描述', 'eventdescription', 'desc', '详情'])
    category_col = _find_col_from_map(col_map, ['事件类型', 'topic', 'category', 'type', 'eventtype', '事件分类'])
    start_date_col = _find_col_from_map(col_map, ['startdate', 'start_date', '开始日期', '开始时间'])
    end_date_col = _find_col_from_map(col_map, ['enddate', 'end_date', '结束日期', '结束时间'])
    keywords_col = _find_col_from_map(col_map, ['eventkeywords', 'keywords', '关键词'])
    impact_col = _find_col_from_map(col_map, ['impact', '影响', 'impactrange', '影响范围'])
    link_col = _find_col_from_map(col_map, ['link', '链接', 'url'])
    location_col = _find_col_from_map(col_map, ['地点', '场馆', 'location', 'venue', 'address'])
    source_col = _find_col_from_map(col_map, ['来源', 'source', 'publisher', '媒体'])

    if not headline_col:
        logger.warning("[城市活动列表] 未找到事件名称列，无法处理")
        return []

    logger.info(
        f"[城市活动列表] 读取到 {len(df)} 行, "
        f"Priority列={priority_col}, 名称列={headline_col}, 描述列={desc_col}"
    )

    def _is_major_city_list_concert(event: dict) -> bool:
        text = " ".join(str(v or "") for v in event.values()).lower()
        if not any(k in text for k in ["演唱会", "concert", "音乐嘉年华"]):
            return False
        if any(k in text for k in ["音乐会", "choral concert", "合唱音乐会", "交响", "室内乐", "独奏", "livehouse", "live house"]):
            return False
        large_markers = [
            "鸟巢", "国家体育场", "国家体育馆", "首都体育馆", "凯迪拉克中心",
            "五棵松", "华熙", "工人体育场", "工体", "国家网球中心", "钻石球场",
            "体育馆", "体育场",
        ]
        return any(k.lower() in text for k in large_markers)

    high_events = []
    empty_priority_events = []
    auto_kept_events = []

    for _, row in df.iterrows():
        event = {}
        for col in df.columns:
            val = row.get(col)
            if val is None or (hasattr(val, '__iter__') and not isinstance(val, str)):
                val = ""
            else:
                try:
                    if pd.isna(val):
                        val = ""
                    else:
                        val = str(val).strip()
                except (ValueError, TypeError):
                    val = ""
            event[col] = val

        priority_val = str(row.get(priority_col, "")).strip().lower() if priority_col else ""

        if priority_val == "high":
            high_events.append(event)
        elif _is_major_city_list_concert(event):
            event["Priority"] = "High"
            auto_kept_events.append(event)
        elif not priority_val or priority_val in ("", "nan", "none", "null"):
            empty_priority_events.append(event)

    logger.info(
        f"[城市活动列表] High={len(high_events)}, "
        f"大型演唱会自动保留={len(auto_kept_events)}, "
        f"Priority为空={len(empty_priority_events)}"
    )

    # Filter empty-priority events via LLM
    filtered_empty = []
    if empty_priority_events:
        client = get_llm_client()
        model = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")
        batch_size = 30

        for i in range(0, len(empty_priority_events), batch_size):
            batch = empty_priority_events[i:i + batch_size]
            batch_text = "\n---\n".join(
                f"{idx+1}. 事件类型: {e.get(category_col, '未知') if category_col else '未知'}\n"
                f"   事件名称: {e.get(headline_col, '')}\n"
                f"   描述: {e.get(desc_col, '') if desc_col else '无'}"
                for idx, e in enumerate(batch)
            )

            filter_prompt = (
                "你是一位严格的事件筛选助手。以下是一批城市活动事件，"
                "请根据事件名称、事件类型和描述判断每个事件是否值得保留。\n\n"
                "【核心原则】默认排除，只有明显符合条件的事件才保留。宁缺毋滥！\n\n"
                "【保留标准】必须满足以下任一条件才可保留：\n"
                "1. 大型展会/博览会/交易会（参展商多、规模大、有行业影响力）\n"
                "2. 国际级或国家级体育赛事（奥运、世界杯、职业联赛、马拉松等）\n"
                "3. 大型文化节/艺术节/电影节（市级及以上规模）\n"
                "4. 政府会议/政策发布/行业峰会（有官方背景）\n"
                "5. 法定节假日/大型节庆活动（影响广泛）\n"
                "6. 明确具有旅游影响（交通管制、景区关闭、酒店紧张等）\n"
                "7. 明确具有公共安全影响（道路封闭、人流管制等）\n\n"
                "【必须排除】以下类型一律丢弃：\n"
                "- 儿童剧/亲子剧/儿童演出（小型商业演出）\n"
                "- 脱口秀/开放麦/单口喜剧（小型商业演出）\n"
                "- 日常驻场演出（如刘老根大舞台、德云社常规场次）\n"
                "- 沉浸式戏剧/密室逃脱/剧本杀类演出\n"
                "- 小型Livehouse音乐会/个人小型演唱会（非大型巡演）\n"
                "- 社区活动/公园常规科普/周末市集\n"
                "- 博物馆常规常设展览（非特展/大型临展）\n"
                "- 普通游园/赏花/徒步活动（无特殊影响）\n"
                "- 任何名称中带有'脱口秀''儿童剧''开放麦''驻场''常规'等字样的活动\n"
                "- 任何没有明确旅游影响或公共安全影响的小型商业演出\n\n"
                f"请对以下 {len(batch)} 个事件逐一严格判断，只返回编号列表。\n"
                "格式：保留: 1,3,5,7\n"
                "丢弃: 2,4,6\n\n"
                f"{batch_text}"
            )

            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": filter_prompt}],
                    temperature=0.1,
                )
                resp_text = resp.choices[0].message.content or ""

                keep_nums = set()
                for line in resp_text.split("\n"):
                    line = line.strip()
                    if line.lower().startswith("保留") or line.lower().startswith("keep"):
                        nums = re.findall(r"\d+", line)
                        keep_nums.update(int(n) for n in nums)

                for idx, event in enumerate(batch):
                    if (idx + 1) in keep_nums:
                        filtered_empty.append(event)

                logger.info(
                    f"[城市活动列表] LLM筛选 batch {i//batch_size+1}: "
                    f"{len(batch)}个 → 保留{len([e for idx, e in enumerate(batch) if (idx+1) in keep_nums])}个"
                )
            except Exception as e:
                logger.warning(f"[城市活动列表] LLM筛选失败 batch {i//batch_size+1}: {e}")

    all_kept = high_events + auto_kept_events + filtered_empty
    logger.info(f"[城市活动列表] 最终保留 {len(all_kept)} 个事件")

    # Topic → standard 8-category mapping (city activity list uses non-standard Topic names)
    _TOPIC_TO_CATEGORY = {
        "展会活动": "大型会议和展览",
        "博物馆展览": "大型会议和展览",
        "会议": "大型会议和展览",
        "展览": "大型会议和展览",
        "体育赛事": "体育赛事",
        "体育": "体育赛事",
        "赛事": "体育赛事",
        "文化演出": "文娱活动",
        "文娱": "文娱活动",
        "演出": "文娱活动",
        "音乐节": "文娱活动",
        "电影节": "文娱活动",
        "节假日": "节假日节庆",
        "节庆": "节假日节庆",
        "政府会议": "高级别政府会议",
        "天气": "极端天气及自然灾害",
        "自然灾害": "极端天气及自然灾害",
        "进出京": "进出京政策",
    }

    def _format_date(val) -> str:
        if not val or val == "":
            return ""
        if hasattr(val, "strftime"):
            return f"{val.year}/{val.month}/{val.day}"
        s = str(val).strip()
        from datetime import datetime
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(s, fmt)
                return f"{dt.year}/{dt.month}/{dt.day}"
            except ValueError:
                continue
        return s

    standard_events = []
    for event in all_kept:
        std_event = {}

        topic_val = event.get(category_col, "") if category_col else ""
        mapped_category = _TOPIC_TO_CATEGORY.get(topic_val, topic_val)
        # Ensure final value is one of the 8 standard categories
        if mapped_category in CATEGORIES:
            std_event["事件类型"] = get_category_type_name(mapped_category)
        else:
            std_event["事件类型"] = _normalize_category(mapped_category)

        for orig_col, std_col in [
            (headline_col, "Headline"),
            (desc_col, "Event Description"),
            (link_col, "Link"),
            (keywords_col, "Event Keywords"),
            (impact_col, "Impact"),
            (priority_col, "Priority"),
            (location_col, "备注/地点"),
            (source_col, "来源"),
        ]:
            if orig_col and orig_col in event:
                std_event[std_col] = event[orig_col]
            else:
                std_event[std_col] = ""

        if event.get("Priority"):
            std_event["Priority"] = event.get("Priority", "")

        if start_date_col and start_date_col in event:
            std_event["Start Date"] = _format_date(event[start_date_col])
        else:
            std_event["Start Date"] = ""
        if end_date_col and end_date_col in event:
            std_event["End Date"] = _format_date(event[end_date_col])
        else:
            std_event["End Date"] = ""

        for k, v in event.items():
            if k not in std_event:
                std_event[k] = v

        std_event["_source"] = "city_activity_list"
        std_event["_raw_category"] = category
        standard_events.append(std_event)

    return standard_events


def _find_col_from_map(col_map: dict, candidates: list[str]) -> Optional[str]:
    """Find first matching column from normalized column name map."""
    for key in candidates:
        if key in col_map:
            return col_map[key]
    return None


def _deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Deduplicate events by city+date+type combination."""
    if not events:
        return events

    seen = {}
    result = []
    for event in events:
        headline = str(event.get("Headline", "")).strip()
        start_date = str(event.get("Start Date", "")).strip()
        end_date = str(event.get("End Date", "")).strip()
        event_type = str(event.get("事件类型", "")).strip()
        event_keywords = str(event.get("Event Keywords", "")).strip()

        city = _extract_city_from_headline(headline)
        if not city:
            city = _extract_city_from_headline(event_keywords)

        key = f"{city}|{start_date}|{end_date}|{event_type}"

        if not city:
            key = f"{headline}|{start_date}|{end_date}"

        if key not in seen:
            seen[key] = len(result)
            result.append(event)
        else:
            existing_idx = seen[key]
            existing_source = str(result[existing_idx].get("_source", "")).strip()
            new_source = str(event.get("_source", "")).strip()
            if new_source == "city_activity_list" and existing_source != "city_activity_list":
                result[existing_idx] = event
                logger.info(f"Deduplication: replaced with city_activity_list version for key={key}")

    logger.info(f"Deduplication: {len(events)} events → {len(result)} unique events")
    return result


def _postprocess_events(events: List[Dict], effective_category: str) -> List[Dict]:
    """Post-process: unify event type field + field name mapping."""
    if effective_category:
        type_name = get_category_type_name(effective_category)
        for event in events:
            event["事件类型"] = type_name
    else:
        for event in events:
            if not event.get("事件类型"):
                event["事件类型"] = "自动判断"
            else:
                # Normalize non-standard category names to one of the 8 standard categories
                event["事件类型"] = _normalize_category(event["事件类型"])

    for event in events:
        if "备注" in event and "备注/地点" not in event:
            event["备注/地点"] = event.pop("备注")
        event.pop("Headline.1", None)

    return events


# Map of non-standard category names → standard 8-category names
_CATEGORY_NORMALIZE_MAP = {
    "博物馆展览": "大型会议和展览",
    "展会活动": "大型会议和展览",
    "会议": "大型会议和展览",
    "展览": "大型会议和展览",
    "文化演出": "文娱活动",
    "演出": "文娱活动",
    "音乐节": "文娱活动",
    "电影节": "文娱活动",
    "演唱会": "文娱活动",
    "节假日": "节假日节庆",
    "节庆": "节假日节庆",
    "天气": "极端天气及自然灾害",
    "自然灾害": "极端天气及自然灾害",
}


def _normalize_category(event_type_value: str) -> str:
    """
    Normalize event type field to one of the 8 standard categories.
    Input may be in format "中文名\\n英文名" or just "中文名".
    """
    if not event_type_value:
        return event_type_value

    s = str(event_type_value).strip()
    # Extract Chinese category name (before \n or \\n)
    if "\n" in s:
        chinese_name = s.split("\n", 1)[0].strip()
    elif "\\n" in s:
        chinese_name = s.split("\\n", 1)[0].strip()
    else:
        chinese_name = s

    # Already one of the 8 standard categories
    if chinese_name in CATEGORIES:
        return get_category_type_name(chinese_name)

    # Try to map to standard category
    mapped = _CATEGORY_NORMALIZE_MAP.get(chinese_name)
    if mapped:
        return get_category_type_name(mapped)

    # Try fuzzy keyword match
    for keyword, target in _CATEGORY_NORMALIZE_MAP.items():
        if keyword in chinese_name:
            return get_category_type_name(target)
    for standard_cat in CATEGORIES:
        if standard_cat in chinese_name or chinese_name in standard_cat:
            return get_category_type_name(standard_cat)

    # Unknown — leave as-is
    return event_type_value


def count_policy_events(events: List[Dict]) -> int:
    """Count high-priority events."""
    count = 0
    for event in events:
        if str(event.get("Priority", "")).lower() == "high":
            count += 1
    return count
