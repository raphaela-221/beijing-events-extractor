/* =========================================================================
   北京大事件 · 共享脚本
   用途：i18n、信号分析、关注列表、弹窗、报告导出
   设计：所有页面通过 <script src="common.js"> 引入，函数直接挂在全局
   ========================================================================= */

/* ---- 常量 ---- */
const TOPIC_COLORS = {
  "中小学假期": "#15803D",
  "体育赛事": "#65A30D",
  "文娱活动": "#0891B2",
  "大型会议和展览": "#4F46E5",
  "高级别政府会议": "#312E81",
  "极端天气及自然灾害": "#B91C1C",
  "节假日节庆": "#F59E0B"
};

/* 活动类型中文名 -> 英文名（英文版渲染时切换；data-topic 颜色 key 仍用中文，不变） */
const TOPIC_EN = {
  "中小学假期": "K-12 Seasonal Breaks",
  "体育赛事": "Sports Events",
  "文娱活动": "Cultural and Entertainment Activities",
  "大型会议和展览": "Significant Conferences and Exhibitions",
  "高级别政府会议": "High-profile Government Meetings",
  "极端天气及自然灾害": "Extreme Weather & Natural Disasters",
  "节假日节庆": "Holiday Celebrations"
};
function topicName(zh){
  if(!zh) return "";
  if(getLang() !== 'en') return zh;
  return TOPIC_EN[zh] || zh;
}
/* 中小学假期 事件细分标签：春秋假 / 寒暑假。类别层已合并为单一"中小学假期"
   大 topic（同色同图例），细分仅在事件级（弹窗/列表/报告）展示，其它类别返回空。 */
function topicSubtag(e, lang){
  const sub = (e && e.topic_subtype) || "";
  if(!sub) return "";
  if(lang === "en"){
    const m = { "春秋假": "Spring/Autumn", "寒暑假": "Winter/Summer" };
    return m[sub] || sub;
  }
  return sub;
}

const DAY_MS = 86400000;

const DOW = [
  ["一", false],
  ["二", false],
  ["三", false],
  ["四", false],
  ["五", false],
  ["六", true],
  ["日", true]
];

const ICONS = {
  close: '<i class="ph ph-x"></i>',
  ext: '<i class="ph ph-arrow-square-out"></i>',
  caretRight: '<i class="ph ph-caret-right"></i>',
  caretLeft: '<i class="ph ph-caret-left"></i>',
  calendar: '<i class="ph ph-calendar-blank"></i>',
  chart: '<i class="ph ph-chart-bar-horizontal"></i>',
  arrowLeft: '<i class="ph ph-arrow-left"></i>',
  download: '<i class="ph ph-download-simple"></i>',
  warning: '<i class="ph ph-warning"></i>'
};

/* ---- MECE 信号定义 ----
   每个原始 topic_zh 只能属于一个信号 */
const SIGNALS = [
  {
    key: "culture",
    zh: "文旅热度",
    en: "Cultural & Tourism Heat",
    topics: ["文娱活动", "节假日节庆", "中小学假期"],
    color: "#0891B2",
    desc_zh: "反映演唱会、演出、节假日与假期等文旅活动的数量与集中程度。",
    desc_en: "Reflects the count and concentration of concerts, shows, holidays, and school breaks."
  },
  {
    key: "venue",
    zh: "赛会密度",
    en: "Sports & Convention Density",
    topics: ["体育赛事", "大型会议和展览"],
    color: "#4F46E5",
    desc_zh: "反映体育赛事与大型会议展览的集中程度，不预设具体地点影响。",
    desc_en: "Reflects the concentration of sports events and large conferences/exhibitions without assuming location impacts."
  },
  {
    key: "gov",
    zh: "政务强度",
    en: "Government Agenda",
    topics: ["高级别政府会议"],
    color: "#312E81",
    desc_zh: "反映高级别政府会议的数量，用于识别政务与安保敏感时段。",
    desc_en: "Reflects the count of high-level government meetings to identify policy and security-sensitive periods."
  },
  {
    key: "risk",
    zh: "公共安全风险",
    en: "Public Safety Risk",
    topics: ["极端天气及自然灾害"],
    color: "#B91C1C",
    desc_zh: "反映极端天气与自然灾害事件数量，用于提示城市运行风险。",
    desc_en: "Reflects the count of extreme weather and natural disaster events as a city-operation risk signal."
  }
];

/* ---- 信号内容描述（用于月度主基调，从事件类别切入） ---- */
const SIGNAL_SUBTOPICS = {
  culture: {
    zh: { "文娱活动": "演唱会与演出", "节假日节庆": "节假日活动", "中小学假期": "中小学假期" },
    en: { "文娱活动": "concerts & shows", "节假日节庆": "holiday events", "中小学假期": "K-12 breaks" }
  },
  venue: {
    zh: { "体育赛事": "体育赛事", "大型会议和展览": "大型会展" },
    en: { "体育赛事": "sports events", "大型会议和展览": "conferences & exhibitions" }
  },
  gov: {
    zh: { "高级别政府会议": "高级别政府会议" },
    en: { "高级别政府会议": "high-level government meetings" }
  },
  risk: {
    zh: { "极端天气及自然灾害": "极端天气与自然灾害" },
    en: { "极端天气及自然灾害": "extreme weather & natural disasters" }
  }
};

const SIGNAL_NARRATIVE = {
  culture: { zh: "文旅活动集中", en: "cultural and tourism events are concentrated" },
  venue:   { zh: "赛会及会展活动密集", en: "sports and convention events are dense" },
  gov:     { zh: "政务会议密集", en: "government meetings are concentrated" },
  risk:    { zh: "公共安全事件需要关注", en: "public safety events need attention" }
};

/* ---- 可覆盖的月度主基调 ---- */
const MONTHLY_THEMES = {
  "2026-03": {
    "zh": "三月北京进入“两会时间”与展会旺季，两会、多场大型展览、体育赛事及文娱活动密集举办，城市活力显著提升。",
    "en": "In March, Beijing entered the 'Two Sessions' period and exhibition peak season, with intensive large-scale conferences, exhibitions, sports events, and entertainment activities significantly boosting urban vitality."
  },
  "2026-01": {
    "zh": "本月北京会展与文体活动密集，国家体育馆、华熙LIVE·五棵松及亦庄会展中心等场馆迎来多场大型赛事、演出和展览，城市活力充沛。",
    "en": "This month, Beijing sees a dense schedule of exhibitions, cultural and sports events, with major venues like the National Indoor Stadium, Huaxi LIVE·Wukesong, and Yizhuang Convention Center hosting large-scale competitions, performances, and exhibitions, showcasing vibrant urban energy."
  },
  "2026-04": {
    "zh": "四月北京迎来会展与体育赛事高峰，北京国际电影节、北京车展、多场马拉松及演唱会密集上演，城市活力全面释放。",
    "en": "In April, Beijing sees a peak of exhibitions and sports events, with the Beijing International Film Festival, Auto China, multiple marathons and concerts creating a vibrant urban pulse."
  },
  "2026-05": {
    "zh": "五月北京文体活动密集，国际赛事与高端会展交织，城市活力充沛。",
    "en": "In May, Beijing is bustling with a dense mix of cultural and sports events, international competitions, and high-end exhibitions, showcasing the city's vibrant pulse."
  },
  "2026-06": {
    "zh": "六月北京迎来国际会议、展览、演出与体育赛事密集叠加的超级活动月，城市活力全面迸发。",
    "en": "In June, Beijing experienced a super-intensive month of international conferences, exhibitions, performances, and sports events, with the city's vitality fully unleashed."
  },
  "2026-07": {
    "zh": "七月北京迎来暑期高峰，大型会议、体育赛事与文娱活动密集举办，叠加全国多地中小学暑假启动，预计将显著带动本地旅游与消费热度。",
    "en": "In July, Beijing enters its summer peak season with a dense schedule of major conferences, sports events, and entertainment activities, while the start of summer vacations for primary and secondary schools nationwide is expected to significantly boost local tourism and consumption."
  },
  "2026-08": {
    "zh": "本月北京体育赛事与大型展览密集举办，城市活力充沛。",
    "en": "This month, Beijing hosts a dense schedule of sports events and large-scale exhibitions, showcasing vibrant urban energy."
  },
  "2026-09": {
    "zh": "九月北京迎来国际篮联洲际杯连续三年落户、服贸会及多场大型工业与消费类展会，城市会展与体育赛事活力集中释放。",
    "en": "In September, Beijing hosts the FIBA Intercontinental Cup for three consecutive years, the CIFTIS, and multiple large-scale industrial and consumer exhibitions, showcasing a concentrated release of urban vitality in conventions and sports events."
  },
  "2026-10": {
    "zh": "十月北京迎来多项大型体育赛事，从亦庄GT世界挑战赛到鸟巢马术大师赛，再到工体足球联赛，城市体育脉搏强劲跳动。",
    "en": "In October, Beijing hosts multiple major sports events, from the Yizhuang GT World Challenge to the Bird's Nest Equestrian Masters and the Workers' Stadium football league, showcasing the city's vibrant sports pulse."
  },
  "2024-01": {
    "zh": "本月，北京市发布龙年春节文化活动安排，节日氛围渐浓。",
    "en": "This month, Beijing announced its Spring Festival cultural activities for the Year of the Dragon, with festive atmosphere building up."
  },
  "2024-02": {
    "zh": "本月北京春节庙会活动丰富，厂甸庙会与地坛庙会相继举办，为市民和游客带来浓厚的京味年节氛围。",
    "en": "This month, Beijing's Spring Festival temple fairs were vibrant, with the Changdian Temple Fair and Ditan Temple Fair successively held, bringing a strong traditional Beijing festive atmosphere to residents and visitors."
  },
  "2024-03": {
    "zh": "本月北京进入全国两会时间，城市运行围绕重大政治会议展开，交通与安保措施加强。",
    "en": "This month, Beijing entered the season of the Two Sessions, with urban operations centered around major political meetings, leading to enhanced traffic and security measures."
  },
  "2024-04": {
    "zh": "四月北京迎来体育、文化、展览三大盛事，城市脉搏因大型活动密集举办而加速跳动。",
    "en": "In April, Beijing witnessed three major events in sports, culture, and exhibitions, with the city's pulse quickening due to the密集 schedule of large-scale activities."
  },
  "2024-05": {
    "zh": "五月北京文体活动密集，鸟巢与工体接连上演演唱会与足球赛，同时举办中阿合作论坛部长级会议，城市脉搏在活力与开放中跳动。",
    "en": "In May, Beijing saw a dense schedule of cultural and sports events at the Bird's Nest and Workers' Stadium, alongside the China-Arab States Cooperation Forum ministerial meeting, reflecting a vibrant and open urban pulse."
  },
  "2024-06": {
    "zh": "本月北京大型文体活动密集，鸟巢和工人体育场分别举办顶级演唱会及两场中超联赛，带动城市活力与场馆周边人流。",
    "en": "This month, Beijing saw a concentration of major cultural and sports events, with the Bird's Nest hosting a top-tier concert and the Workers' Stadium holding two Chinese Super League matches, boosting urban vitality and foot traffic around the venues."
  },
  "2024-07": {
    "zh": "7月北京迎来党的二十届三中全会，同时中超联赛、薛之谦及刘德华演唱会等大型文体活动密集举办，但暴雨黄色预警对部分户外活动和交通造成一定影响。",
    "en": "In July, Beijing hosted the Third Plenary Session of the 20th Central Committee of the CPC, alongside密集 large-scale cultural and sports events such as the Chinese Super League and concerts by Xue Zhiqian and Andy Lau, while a yellow rainstorm warning affected some outdoor activities and transportation."
  },
  "2024-08": {
    "zh": "八月北京大型文体活动密集，国家体育场和工人体育场接连举办多场演唱会及足球赛事，持续带动场馆周边人流与城市活力。",
    "en": "In August, Beijing saw a密集 schedule of large-scale cultural and sports events, with consecutive concerts and football matches at the National Stadium and Workers' Stadium, continuously boosting foot traffic and urban vitality around the venues."
  },
  "2024-09": {
    "zh": "九月北京迎来中非合作论坛峰会、服贸会、香山论坛等高级别会议，以及华晨宇、周深演唱会、中网、WTT大满贯、中超等文体活动，城市脉搏活跃，国际交往与文体消费并进。",
    "en": "In September, Beijing hosted high-level meetings including the FOCAC Summit, CIFTIS, and Xiangshan Forum, along with cultural and sports events such as Hua Chenyu and Zhou Shen concerts, China Open, WTT Grand Smash, and CSL matches, reflecting a vibrant urban pulse driven by international exchanges and recreational consumption."
  },
  "2024-10": {
    "zh": "十月北京文体活动密集，CBA联赛、中超足球赛及演唱会接连上演，同时金融街论坛年会与全国民政会议等重要会议召开，城市活力充沛。",
    "en": "In October, Beijing saw a dense schedule of cultural and sports events, including CBA league matches, a CSL football game, and a concert, alongside major conferences like the Financial Street Forum and the National Civil Affairs Conference, reflecting vibrant urban dynamics."
  },
  "2024-11": {
    "zh": "11月北京文旅消费博览会、中超足球赛和马拉松相继举办，带动文旅与体育热潮；中央社会工作会议聚焦社会治理；月底国际速度滑冰和单板滑雪大跳台世界杯在冬奥场馆开赛，延续冰雪运动热度。",
    "en": "In November, Beijing hosted the Cultural Tourism Consumption Expo, a CSL football match, and the marathon, boosting cultural tourism and sports; the Central Social Work Conference focused on social governance; late November saw the ISU Speed Skating World Cup and FIS Snowboard & Freestyle Ski Big Air World Cup at Winter Olympic venues, sustaining the ice and snow sports momentum."
  },
  "2024-12": {
    "zh": "本月北京以延庆冰雪赛事和首都体育馆短道速滑世界巡回赛点燃冬季运动热情，同时五棵松两场大型演唱会掀起文娱高潮，城市文体活动双线并进。",
    "en": "This month, Beijing ignited winter sports enthusiasm with ice and snow events in Yanqing and the Short Track Speed Skating World Tour at Capital Indoor Stadium, while two major concerts at Wukesong sparked cultural entertainment highlights, driving a dual-track boom in sports and cultural activities."
  },
  "2025-01": {
    "zh": "2025年1月，北京以春节庙会与近万场文化活动展现古都文化魅力，城市脉搏聚焦节庆氛围与文旅活力。",
    "en": "In January 2025, Beijing showcased its cultural charm through Spring Festival temple fairs and nearly 10,000 cultural events, with the city's pulse centered on festive atmosphere and cultural tourism vitality."
  },
  "2025-02": {
    "zh": "2月，延庆国际冰雪赛事与五棵松演唱会并行，体育与文娱共同点燃城市活力。",
    "en": "In February, international ice and snow events in Yanqing and a concert at Wukesong jointly ignited the city's vitality through sports and entertainment."
  },
  "2025-03": {
    "zh": "本月北京迎来全国两会，同时国家体育馆、五棵松、工人体育场等场馆密集举办篮球、足球赛事及演唱会，城市文体活动与政务会议并行，展现首都多元活力。",
    "en": "This month, Beijing hosted the Two Sessions, while venues like the National Stadium, Wukesong, and Workers' Stadium saw a dense schedule of basketball games, football matches, and concerts, showcasing the capital's diverse vitality alongside political events."
  },
  "2025-04": {
    "zh": "四月北京文体活动密集，但遭遇极端大风天气导致部分高铁停运，月底两大庙会开幕迎接五一。",
    "en": "In April, Beijing saw a dense schedule of cultural and sports events, but was hit by extreme gale winds that led to partial high-speed rail suspensions, while two major temple fairs opened at month's end to welcome the May Day holiday."
  },
  "2025-05": {
    "zh": "五月北京文体赛事与演唱会密集上演，同时遭遇极端大风天气考验，国际经贸峰会亦汇聚全球目光，城市脉搏在活力与挑战中交织。",
    "en": "In May, Beijing witnessed a dense schedule of sports events and concerts, alongside extreme gale weather challenges, while an international trade summit drew global attention, weaving a tapestry of vitality and resilience in the city's pulse."
  },
  "2025-06": {
    "zh": "六月北京迎来亚投行年会、CBD论坛等国际会议，同时国家体育场、国家体育馆、工人体育场及华熙LIVE·五棵松等场馆密集举办多场演唱会和体育赛事，城市文体活动与国际交流热度高涨。",
    "en": "In June, Beijing hosted international events such as the AIIB Annual Meeting and the CBD Forum, while venues like the National Stadium, National Indoor Stadium, Workers' Stadium, and Huaxi LIVE·Wukesong saw a密集 schedule of concerts and sports events, reflecting a vibrant mix of cultural, sports, and international exchange activities."
  },
  "2025-07": {
    "zh": "本月北京迎来多场大型文娱演出、体育赛事和展览活动，同时遭遇多次暴雨预警及红色预警，城市运行面临活动密集与极端天气的双重考验。",
    "en": "This month, Beijing hosted multiple large-scale entertainment performances, sports events, and exhibitions, while facing several rainstorm warnings and a red alert, putting urban operations under the dual pressure of dense activities and extreme weather."
  },
  "2025-08": {
    "zh": "八月北京大型文娱体育赛事密集，同时遭遇暴雨红色预警，城市运行面临双重考验。",
    "en": "In August, Beijing saw a dense schedule of major entertainment and sports events, while facing a red rainstorm warning, putting urban operations under dual pressure."
  },
  "2025-09": {
    "zh": "9月北京迎来阅兵、服贸会、中网、WTT大满贯及多场演唱会和体育赛事，城市脉搏在政治纪念、国际会展与文体盛事中强劲跳动。",
    "en": "In September, Beijing hosts a military parade, CIFTIS, China Open, WTT China Smash, and multiple concerts and sports events, with the city's pulse beating strongly through political commemorations, international exhibitions, and cultural-sports spectacles."
  },
  "2025-10": {
    "zh": "金秋十月，北京文化活动、体育赛事与高端会议密集交织，城市脉搏在多元活力中强劲跳动。",
    "en": "In golden October, Beijing's pulse beats strongly with a dense weave of cultural events, sports competitions, and high-level conferences."
  },
  "2025-11": {
    "zh": "11月北京文体活动密集，国家体育馆、五棵松、工人体育场等场馆迎来多场演唱会、足球赛及国际篮球预选赛，通州半程马拉松同步开跑，城市活力充沛。",
    "en": "In November, Beijing saw a dense schedule of cultural and sports events, with multiple concerts, football matches, and an international basketball qualifier held at venues like the National Stadium, Wukesong, and Workers' Stadium, alongside the Tongzhou Half Marathon, showcasing vibrant urban energy."
  },
  "2025-12": {
    "zh": "12月北京迎来国际滑雪赛事、多场演唱会及亚冠联赛等文体活动密集举办，同时中央经济工作会议在京举行，城市在冰雪运动热潮与年终经济部署中展现活力。",
    "en": "In December, Beijing saw a dense schedule of cultural and sports events including an international skiing competition, multiple concerts, and an AFC Champions League match, alongside the Central Economic Work Conference, showcasing the city's vitality amid winter sports enthusiasm and year-end economic planning."
  },
  "2026-02": {
    "zh": "本月北京以春节文化活动为主线，博物馆展览、庙会灯会、演出等多元形式共同营造浓郁节日氛围。",
    "en": "This month, Beijing's urban pulse is centered around Spring Festival cultural activities, with museum exhibitions, temple fairs, lantern shows, and performances jointly creating a festive atmosphere."
  },
  "2026-11": {
    "zh": "本月外地多个城市中小学秋假集中，有望带动北京亲子游与消费热度；同时工人体育场举办中超联赛，吸引球迷观赛。",
    "en": "This month, multiple cities outside Beijing have concentrated primary and secondary school autumn breaks, which is expected to boost family tourism and consumption in Beijing; meanwhile, the Chinese Super League match at Workers' Stadium attracts fans to the game."
  },
  "2026-12": {
    "zh": "北京获得2026年短池游泳世锦赛举办权，彰显国际体育中心地位。",
    "en": "Beijing secures the hosting rights for the 2026 Short Course Swimming World Championships, highlighting its status as an international sports hub."
  },
  "2027-01": {
    "zh": "本月，外地中小学寒假启动，预计将带动北京亲子游与研学客流，提升城市消费热度。",
    "en": "This month, the start of winter break for primary and secondary schools in other regions is expected to boost family and study tour visits to Beijing, enhancing urban consumption activity."
  },
  "2027-07": {
    "zh": "天津中小学暑假开启，预计将带动北京暑期亲子游与消费热度。",
    "en": "The start of summer vacation for primary and secondary schools in Tianjin is expected to boost Beijing's summer family tourism and consumption."
  },
  "2027-09": {
    "zh": "本月，北京2027年世界田径锦标赛官方新媒体上线，赛事将于国家体育场（鸟巢）举行，城市体育氛围升温，鸟巢周边将迎来显著人流。",
    "en": "This month, the official new media for the 2027 World Athletics Championships in Beijing went live; the event will be held at the National Stadium (Bird's Nest), boosting the city's sports atmosphere and bringing significant crowds around the venue."
  }
};

/* ---- i18n 字典 ---- */
const I18N = {
  zh: {
    searchPlaceholder: "搜索事件标题 / 关键词…",
    typeLabel: "类型",
    backToOverview: "返回总览",
    viewOverview: "整合总览",
    viewMonth: "月历视图",
    viewTimeline: "时间轴视图",
    viewMonthDesc: "整月日历网格，每天显示事件色块，一眼看清「哪天有 High 事件」。",
    viewTimelineDesc: "每条事件横条跨开始–结束日，按类型分泳道，擅长看持续期和重叠。",
    timelineHint: "每条横条从开始日跨到结束日，颜色按类型，按类型分泳道。<b>横向滚动</b>看更远时间，<b>点击横条</b>看详情。红色竖线是今天。",
    openView: "打开",
    openMonthView: "打开月历",
    openTimelineView: "打开时间轴",
    prevMonth: "上一月",
    nextMonth: "下一月",
    nextMonthLabel: "下月",
    monthlyTheme: "本月观察",
    specialAttention: "近期重点关注",
    upcomingTitle: "近期即将发生",
    dataReference: "数据参考",
    totalEvents: "全部事件",
    eventsUnit: "条",
    activeNow: "进行中",
    exportChinese: "导出中文报告",
    exportEnglish: "导出英文报告",
    exportBoth: "导出中英文报告",
    downloadRaw: "事件清单（Excel）",
    noEvents: "暂无事件",
    close: "关闭",
    eventCount: "%n 个事件",
    keywords: "关键词",
    keywordsEn: "Keywords",
    viewSource: "查看来源原文",
    dayUnit: "天",
    today: "今天",
    badge_ongoing: "进行中",
    badge_upcoming: "即将开始",
    badge_publicSafety: "公共安全",
    badge_govtAgenda: "政务密集",
    badge_multiday: "持续多日",
    badge_largeGathering: "人流密集",
    report_title: "北京大事件报告",
    report_generated: "生成时间",
    report_disclaimer: "注：事件标题与正文原文为中文，英文报告仅翻译了分类、关键词与总结。",
    report_signal_header: "城市脉搏信号",
    report_signal_col_signal: "信号",
    report_signal_col_count: "数量",
    report_signal_col_trend: "环比",
    report_watchlist_header: "近期特别关注",
    report_upcoming_header: "近期事件",
    ganttAxisLabel: "类型 / 事件",
    ganttEmpty: "该时间范围内无事件",
    signalCountLabel: "本月相关事件",
    distMonth: "当月分布",
    distAll: "全部事件",
    monthHighlights: "当月重点事件"
  },
  en: {
    searchPlaceholder: "Search headlines / keywords…",
    typeLabel: "Type",
    backToOverview: "Back to overview",
    viewOverview: "Overview",
    viewMonth: "Month View",
    viewTimeline: "Timeline View",
    viewMonthDesc: "Full-month calendar grid with daily event chips to see at a glance which days have High events.",
    viewTimelineDesc: "Each event spans its start-to-end date in topic lanes, ideal for durations and overlaps.",
    timelineHint: "Each bar spans its start-to-end date, colored by type and grouped by topic lane. <b>Scroll horizontally</b> to see more time, <b>click a bar</b> for details. The red line is today.",
    openView: "Open",
    openMonthView: "Open month view",
    openTimelineView: "Open timeline view",
    prevMonth: "Previous month",
    nextMonth: "Next month",
    nextMonthLabel: "Next",
    monthlyTheme: "Monthly Take",
    specialAttention: "Watchlist",
    upcomingTitle: "Coming Up",
    dataReference: "Data reference",
    totalEvents: "Total events",
    eventsUnit: "",
    activeNow: "Active",
    exportChinese: "Export Chinese report",
    exportEnglish: "Export English report",
    exportBoth: "Export both reports",
    downloadRaw: "Event list (Excel)",
    noEvents: "No events",
    close: "Close",
    eventCount: "%n events",
    keywords: "Keywords",
    keywordsEn: "Keywords",
    viewSource: "View source",
    dayUnit: "days",
    today: "Today",
    badge_ongoing: "Ongoing",
    badge_upcoming: "Upcoming",
    badge_publicSafety: "Public safety",
    badge_govtAgenda: "Govt agenda",
    badge_multiday: "Multi-day",
    badge_largeGathering: "Large crowd",
    report_title: "Beijing Major Events Report",
    report_generated: "Generated",
    report_disclaimer: "Note: Event headlines and descriptions remain in Chinese; the English report translates only categories, keywords, and summaries.",
    report_signal_header: "City Pulse Signals",
    report_signal_col_signal: "Signal",
    report_signal_col_count: "Count",
    report_signal_col_trend: "MoM",
    report_watchlist_header: "Watchlist",
    report_upcoming_header: "Upcoming Events",
    ganttAxisLabel: "Type / Event",
    ganttEmpty: "No events in this range",
    signalCountLabel: "Related events this month",
    distMonth: "This month",
    distAll: "All events",
    monthHighlights: "Month highlights"
  }
};

/* ---- i18n 函数 ---- */
function getLang() {
  return localStorage.getItem("cc_lang") || "zh";
}

function setLang(lang) {
  if (lang !== "zh" && lang !== "en") lang = "zh";
  localStorage.setItem("cc_lang", lang);
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
}

function t(key, fallback) {
  return tL(key, getLang(), fallback);
}

function tL(key, lang, fallback) {
  const dict = I18N[lang] || I18N.zh;
  return dict[key] ?? fallback ?? key;
}

function signalName(signal) {
  return getLang() === "en" ? signal.en : signal.zh;
}

function signalDesc(signal) {
  return getLang() === "en" ? signal.desc_en : signal.desc_zh;
}

/* ---- 基础工具 ---- */
function parseDate(s) {
  return new Date(s + "T00:00:00");
}

function stripTime(d) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function fmtDate(d) {
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

function fmtDateEn(d) {
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

function fmtDateL(d, lang) {
  return lang === "en" ? fmtDateEn(d) : fmtDate(d);
}

function esc(s) {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function kwPills(s) {
  if (!s) return "";
  return s
    .split(/[,，、;；\|]/)
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => `<span class="k">${esc(x)}</span>`)
    .join("");
}

function splitKeywords(s) {
  if (!s) return [];
  return s
    .split(/[,，、;；\|\n]/)
    .map((x) => x.trim())
    .filter(Boolean);
}

function eventLabel(e, lang, maxCount = 1) {
  const kwField = lang === "en" ? "keywords_en" : "keywords_zh";
  const kws = splitKeywords(e[kwField]);
  if (kws.length) {
    const joined = kws.slice(0, maxCount).join(" / ");
    if (joined) return joined;
  }
  return e.headline || "";
}

/* ---- 短标签（用于月历格子 / 时间轴条形显示）----
   tooltip 与弹窗仍走 eventLabel() 显示完整关键词，这里只压缩显示文字。
   先取第一个关键词 → 去掉开头年份/赛季前缀 → 套简称规则 → 仍过长则截断。
   简称表按需增删：[/匹配片段/, "简称"]。 */
const SHORT_RULES_ZH = [
  [/中国足球协会超级联赛|中超联赛/, "中超"],
  [/中国男子篮球职业联赛|CBA常规赛/, "CBA"],
  [/中国国际服务贸易交易会/, "服贸会"],
  [/中国国际供应链促进博览会/, "链博会"],
  [/北京国际汽车展览会/, "北京车展"],
  [/北京国际电影节/, "北影节"],
  [/北京国际长跑节|北京半程马拉松/, "半马"],
  [/北京马拉松/, "北马"],
  [/上海合作组织峰会/, "上合峰会"],
  [/全国政协/, "全国政协"],
  [/全国人大/, "全国人大"],
  [/纪念中国人民抗日战争暨世界反法西斯战争胜利/, "抗战胜利"],
  [/中共中央政治局常务委员会/, "政治局常委会"],
  [/党的二十届三中全会/, "三中全会"],
  [/金融街论坛年会/, "金融街论坛"],
  [/WTT中国大满贯/, "WTT大满贯"],
];
const SHORT_RULES_EN = [
  [/Chinese Football Association Super League|CSL/, "CSL"],
  [/Chinese Men's Basketball Professional League|CBA/, "CBA"],
];
function _stripKwPrefix(s) {
  return s
    .replace(/^20\d{2}[—\-至]20\d{2}赛季/, "")
    .replace(/^20\d{2}年/, "")
    .replace(/^20\d{2}/, "")
    .trim();
}
/* 演唱会短标签：从关键词里子串查找演员名，统一输出 "演员名+演唱会"，
   省去年份和巡演名（巡演名可能在演员名前/后，子串查找都能命中）。
   名单按需增删；多人用 & 连接（如 林子祥&叶蒨文演唱会）。 */
const SINGER_NAMES = [
  "凤凰传奇","五月天","莫文蔚","薛之谦","刘德华","张杰","邓紫棋","华晨宇",
  "周深","许嵩","周华健","刀郎","黄明昊","杨丞琳","林志炫","潘玮柏",
  "张惠妹","胡夏","李健","张学友","孙燕姿","王力宏","林俊杰","王栎鑫",
  "徐佳莹","陈奕迅","陈粒","毛不易","张艺兴","伍佰","王心凌","易烊千玺",
  "王源","陈小春","陶喆","张碧晨","韩红","张靓颖","周笔畅","八三夭",
  "威神V","ONER","刘若英","顽童MJ116","郭富城","OneRepublic","谢霆锋",
  "林冰","鹿先森乐队","周杰伦","孙楠","陈立农","丢火车乐队","胡彦斌",
  "韦礼安","周震南","张远","洛天依","林子祥","叶蒨文","蒲熠星","滨崎步",
  "蔡依林","黄丽玲","汪峰","光良","郁可唯","海来阿木","崔健","宝石Gem",
  "薛凯琪","陆虎","毕雯珺","王赫野","颜人中","袁娅维",
];
function concertShort(s) {
  let hits = SINGER_NAMES.filter((n) => s.includes(n));
  if (!hits.length) return null;
  // 去掉被更长名字包含的短名（防止 "张杰" 误命中含 "张杰" 的更长演员名）
  hits.sort((a, b) => b.length - a.length);
  hits = hits.filter((n) => !hits.some((m) => m !== n && m.includes(n)));
  // 按在原文中出现的位置排序，保证 & 顺序自然
  hits.sort((a, b) => s.indexOf(a) - s.indexOf(b));
  return hits.join("&") + "演唱会";
}
function shortLabel(e, lang, opts) {
  const kwField = lang === "en" ? "keywords_en" : "keywords_zh";
  const first = splitKeywords(e[kwField])[0] || "";
  const rules = lang === "en" ? SHORT_RULES_EN : SHORT_RULES_ZH;
  let s = _stripKwPrefix(first);
  if (s.includes("演唱会")) {
    const c = concertShort(s);
    if (c) return c;
  }
  for (const [re, rep] of rules) {
    if (re.test(s)) return rep;
  }
  /* noTruncate：时间轴条形宽度可变（长条够宽），交给 CSS ellipsis 按实际宽度裁剪，
     不在 JS 层硬截 9 字；月历格子空间小，仍走默认 9 字截断。 */
  if ((!opts || !opts.noTruncate) && s.length > 9) s = s.slice(0, 9) + "…";
  return s || e.headline || "";
}

function eventOnDay(e, d) {
  const s = stripTime(parseDate(e.start));
  const t = stripTime(parseDate(e.end));
  return d >= s && d <= t;
}

/* ---- 过滤 ---- */
function filterEvents(events, activeTopics, q) {
  const query = (q || "").toLowerCase();
  return events.filter((e) => {
    if (!activeTopics.has(e.topic_zh)) return false;
    if (!query) return true;
    const hay = (e.headline || "") + (e.keywords_zh || "") + (e.topic_zh || "") + (e.topic_en || "") + (e.keywords_en || "");
    return hay.toLowerCase().includes(query);
  });
}

function eventsInMonth(events, y, m) {
  return events.filter((e) => {
    const d = parseDate(e.start);
    return d.getFullYear() === y && d.getMonth() === m;
  });
}

function computeInitialMonth(events) {
  const now = new Date();
  let y = now.getFullYear();
  let m = now.getMonth();

  // If the current month has any events, stay there.
  if (eventsInMonth(events, y, m).length > 0) {
    return { y, m };
  }

  // Otherwise look forward up to 24 months for a month with more than 15 events.
  for (let i = 0; i < 24; i++) {
    m += 1;
    if (m > 11) {
      m = 0;
      y += 1;
    }
    if (eventsInMonth(events, y, m).length > 15) {
      return { y, m };
    }
  }

  // Fallback: the month with the most events in the dataset.
  const counts = new Map();
  for (const e of events) {
    const d = parseDate(e.start);
    const key = `${d.getFullYear()}-${d.getMonth()}`;
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  let best = { y, m };
  let bestCount = -1;
  for (const [key, c] of counts) {
    const [yy, mm] = key.split("-").map(Number);
    if (c > bestCount) {
      bestCount = c;
      best = { y: yy, m: mm };
    }
  }
  return best;
}

function eventsActiveOn(events, date) {
  const d = stripTime(date);
  return events.filter((e) => eventOnDay(e, d));
}

/* ---- 信号分析 ---- */
function computeSignals(events, y, m) {
  const cur = eventsInMonth(events, y, m);
  const prevDate = new Date(y, m - 1, 1);
  const prev = eventsInMonth(events, prevDate.getFullYear(), prevDate.getMonth());

  return SIGNALS.map((sig) => {
    const count = cur.filter((e) => sig.topics.includes(e.topic_zh)).length;
    const prevCount = prev.filter((e) => sig.topics.includes(e.topic_zh)).length;
    const delta = count - prevCount;
    let trend = "flat";
    if (delta > 0) trend = "up";
    if (delta < 0) trend = "down";
    return { ...sig, count, prevCount, delta, trend };
  });
}

function trendHtml(signal, lang) {
  if (signal.trend === "flat") return `<span class="trend flat">—</span>`;
  const arrow = signal.trend === "up" ? "▲" : "▼";
  const cls = signal.trend === "up" ? "up" : "down";
  const sign = signal.trend === "up" ? "+" : "";
  return `<span class="trend ${cls}">${arrow} ${sign}${signal.delta}</span>`;
}

function trendText(signal, lang) {
  if (signal.trend === "flat") return "—";
  const sign = signal.trend === "up" ? "+" : "";
  return `${sign}${signal.delta}`;
}

/* ---- 月度主基调（从事件类别切入，避免只讲数量） ---- */
function presentSubtopics(signal, events, lang) {
  const map = SIGNAL_SUBTOPICS[signal.key][lang] || SIGNAL_SUBTOPICS[signal.key].zh;
  return signal.topics
    .filter((t) => events.some((e) => e.topic_zh === t))
    .map((t) => map[t] || t);
}

function getMonthlyTheme(events, y, m) {
  const key = `${y}-${String(m + 1).padStart(2, "0")}`;
  if (MONTHLY_THEMES[key]) return MONTHLY_THEMES[key];

  const monthEvents = eventsInMonth(events, y, m);
  if (!monthEvents.length) {
    return { zh: "本月暂无事件。", en: "No events this month." };
  }

  const signals = computeSignals(events, y, m);
  const sorted = [...signals].sort((a, b) => b.count - a.count);
  const top = sorted[0];
  const riskSignal = signals.find((s) => s.key === "risk");
  const hasRisk = monthEvents.some((e) => e.topic_zh === "极端天气及自然灾害");
  const govSoon = events
    .filter((e) => e.topic_zh === "高级别政府会议")
    .some((e) => {
      const s = stripTime(parseDate(e.start));
      const today = stripTime(new Date());
      const diff = Math.round((s - today) / DAY_MS);
      return diff >= 0 && diff <= 7;
    });

  const topSubsZh = presentSubtopics(top, monthEvents, "zh");
  const topSubsEn = presentSubtopics(top, monthEvents, "en");

  // 中文
  let zh = "本月北京";
  if (top.key === "risk") {
    zh += `需重点关注${top.zh}`;
    if (topSubsZh.length) zh += `，${topSubsZh.join("、")}较为突出`;
    zh += `，${SIGNAL_NARRATIVE.risk.zh}`;
  } else {
    zh += `以${top.zh}为主线`;
    if (topSubsZh.length) zh += `，${topSubsZh.join("、")}较为集中`;
    zh += `，${SIGNAL_NARRATIVE[top.key].zh}`;
  }
  if (top.key !== "risk" && hasRisk) {
    const riskSubs = presentSubtopics(riskSignal, monthEvents, "zh");
    zh += `；同时需防范${riskSubs.join("、")}影响`;
  }
  if (top.key !== "gov" && govSoon) zh += "；高级别政府会议临近，需关注政务与安保安排";
  zh += "。";

  // 英文
  let en = "This month in Beijing";
  if (top.key === "risk") {
    en += ` is marked by ${top.en}`;
    if (topSubsEn.length) en += `, with ${topSubsEn.join(", ")} standing out`;
    en += `; ${SIGNAL_NARRATIVE.risk.en}`;
  } else {
    en += ` is dominated by ${top.en}`;
    if (topSubsEn.length) en += `, where ${topSubsEn.join(", ")} cluster`;
    en += `; ${SIGNAL_NARRATIVE[top.key].en}`;
  }
  if (top.key !== "risk" && hasRisk) {
    const riskSubsEn = presentSubtopics(riskSignal, monthEvents, "en");
    en += `; also watch for ${riskSubsEn.join(", ")}`;
  }
  if (top.key !== "gov" && govSoon) en += "; high-level government meetings are approaching, so monitor policy and security arrangements";
  en += ".";

  return { zh, en };
}

/* ---- 关注列表 ---- */
function getWatchlist(events, opts) {
  const today = stripTime(opts && opts.today ? opts.today : new Date());
  const limit = new Date(today.getTime() + 60 * DAY_MS);

  const topicWeight = {
    "极端天气及自然灾害": 100,
    "高级别政府会议": 80,
    "体育赛事": 40,
    "大型会议和展览": 35,
    "文娱活动": 20,
    "节假日节庆": 15,
    "中小学假期": 10
  };

  const scored = events
    .map((e) => {
      const s = stripTime(parseDate(e.start));
      const en = stripTime(parseDate(e.end));
      const ongoing = s <= today && en >= today;
      const upcoming = s >= today && s <= limit;
      if (!ongoing && !upcoming) return null;

      const days = Math.round((en - s) / DAY_MS) + 1;
      const diff = Math.round((s - today) / DAY_MS);

      let score = topicWeight[e.topic_zh] || 10;
      if (ongoing) score += 50;
      else if (diff <= 7) score += 40;
      else if (diff <= 14) score += 30;
      else if (diff <= 30) score += 20;
      else score += 10;

      if (days >= 7) score += 20;
      else if (days >= 3) score += 10;

      const badges = [];
      if (ongoing) badges.push("ongoing");
      else if (upcoming) badges.push("upcoming");
      if (e.topic_zh === "极端天气及自然灾害") badges.push("publicSafety");
      if (e.topic_zh === "高级别政府会议") badges.push("govtAgenda");
      if (["体育赛事", "大型会议和展览"].includes(e.topic_zh) && (ongoing || diff <= 14)) {
        badges.push("largeGathering");
      }
      if (days >= 3) badges.push("multiday");

      return { event: e, score, badges, days };
    })
    .filter(Boolean);

  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return parseDate(a.event.start).getTime() - parseDate(b.event.start).getTime();
  });

  return scored.slice(0, 10);
}

/* ---- 当月代表事件（填补左侧面板并帮助快速定位重点） ---- */
function getMonthHighlights(events, y, m) {
  const today = stripTime(new Date());
  const monthEvents = eventsInMonth(events, y, m);
  const topicWeight = {
    "极端天气及自然灾害": 100,
    "高级别政府会议": 80,
    "体育赛事": 40,
    "大型会议和展览": 35,
    "文娱活动": 20,
    "节假日节庆": 15,
    "中小学假期": 10
  };

  const scored = monthEvents
    .map((e) => {
      const s = stripTime(parseDate(e.start));
      const en = stripTime(parseDate(e.end));
      const ongoing = s <= today && en >= today;
      const days = Math.round((en - s) / DAY_MS) + 1;

      let score = topicWeight[e.topic_zh] || 10;
      if (ongoing) score += 30;
      if (days >= 7) score += 15;
      else if (days >= 3) score += 8;

      return { event: e, score };
    })
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return parseDate(a.event.start).getTime() - parseDate(b.event.start).getTime();
    });

  return scored.slice(0, 5);
}

function badgeHtml(badgeKey) {
  const label = t(`badge_${badgeKey}`);
  return `<span class="badge" data-badge="${badgeKey}">${esc(label)}</span>`;
}

/* ---- 弹窗 ---- */
function openByNo(no) {
  const e = window.EVENTS && window.EVENTS.find((x) => x.no === no);
  if (e) openModal(e);
}

function openModal(e) {
  const modal = document.getElementById("modal");
  const modalBg = document.getElementById("modalBg");
  if (!modal || !modalBg) return;

  const lang = getLang();
  const multi = e.start !== e.end;
  const days = Math.round((stripTime(parseDate(e.end)) - stripTime(parseDate(e.start))) / DAY_MS) + 1;
  const startLabel = fmtDateL(parseDate(e.start), lang);
  const endLabel = fmtDateL(parseDate(e.end), lang);

  const keywordsSection = e.keywords_zh
    ? `<div class="sect-lab">${t("keywords")}</div><div class="kw">${kwPills(e.keywords_zh)}</div>`
    : "";
  const keywordsEnSection = e.keywords_en
    ? `<div class="sect-lab">${t("keywordsEn")}</div><div class="kw en">${kwPills(e.keywords_en)}</div>`
    : "";
  const linkSection = e.link
    ? `<a class="link" href="${esc(e.link)}" target="_blank" rel="noopener">${t("viewSource")} ${ICONS.ext}</a>`
    : "";

  modal.innerHTML = `
    <button class="close" onclick="closeModal()" aria-label="${t("close")}">${ICONS.close}</button>
    <span class="topic-badge" data-topic="${e.topic_zh}">
      <span class="swatch"></span>${e.topic_zh}${e.topic_en ? `<span class="en">· ${esc(e.topic_en)}</span>` : ""}${topicSubtag(e, getLang()) ? `<span class="sub">· ${esc(topicSubtag(e, getLang()))}</span>` : ""}
    </span>
    <h2>${esc(e.headline)}</h2>
    <div class="meta">
      <span class="date">${startLabel}</span>
      ${multi ? `<span class="date">→ ${endLabel}</span><span class="dur">${days} ${t("dayUnit")}</span>` : ""}
    </div>
    ${e.description ? `<div class="desc">${esc(e.description)}</div>` : ""}
    ${keywordsSection}
    ${keywordsEnSection}
    ${linkSection}`;
  modalBg.classList.add("show");
}

function closeModal() {
  const modalBg = document.getElementById("modalBg");
  if (modalBg) modalBg.classList.remove("show");
}

function openDayModal(y, m, d, events) {
  const modal = document.getElementById("modal");
  const modalBg = document.getElementById("modalBg");
  if (!modal || !modalBg) return;
  const date = stripTime(new Date(y, m, d));
  const de = filterEvents(events, new Set(Object.keys(TOPIC_COLORS)), "").filter((e) => eventOnDay(e, date));
  const lang = getLang();
  const dateLabel = fmtDateL(date, lang);

  modal.innerHTML = `
    <button class="close" onclick="closeModal()" aria-label="${t("close")}">${ICONS.close}</button>
    <h2>${dateLabel} · ${t("eventCount").replace("%n", de.length)}</h2>
    <div class="day-list">${de
      .map(
        (e) => `
      <div class="item" data-topic="${e.topic_zh}" onclick="openByNo(${e.no})">
        <div class="top"><span class="swatch"></span>${topicName(e.topic_zh)}${topicSubtag(e, getLang()) ? ` · ${topicSubtag(e, getLang())}` : ""}<span class="dt">${e.start}</span></div>
        <div class="ti">${esc(eventLabel(e, getLang(), 2))}</div>
      </div>`
      )
      .join("")}</div>`;
  modalBg.classList.add("show");
}

/* ---- 筛选 chips 渲染 ---- */
function renderFilters(containerId, activeTopics, onChange) {
  const f = document.getElementById(containerId);
  if (!f) return;
  f.innerHTML = `<span class="lab">${t("typeLabel")}</span>`;
  Object.keys(TOPIC_COLORS).forEach((t) => {
    const ch = document.createElement("div");
    ch.className = "chip" + (activeTopics.has(t) ? "" : " off");
    ch.dataset.topic = t;
    ch.innerHTML = `<span class="swatch"></span>${topicName(t)}`;
    ch.onclick = () => {
      if (activeTopics.has(t)) activeTopics.delete(t);
      else activeTopics.add(t);
      onChange();
    };
    f.appendChild(ch);
  });
}

/* ---- 报告导出 ---- */
function buildReport(events, y, m, lang) {
  const signals = computeSignals(events, y, m);
  const theme = getMonthlyTheme(events, y, m);
  const watchlist = getWatchlist(events);
  const today = stripTime(new Date());
  const upcoming = events
    .filter((e) => stripTime(parseDate(e.start)) >= today)
    .sort((a, b) => a.start.localeCompare(b.start))
    .slice(0, 15);

  const dateStr = lang === "en" ? fmtDateEn(new Date()) : fmtDate(new Date());

  const signalRows = signals
    .map((s) => {
      const name = lang === "en" ? s.en : s.zh;
      const count = s.count;
      const trend = trendText(s, lang);
      return `| ${name} | ${count} | ${trend} |`;
    })
    .join("\n");

  const watchlistRows = watchlist
    .map((w) => {
      const e = w.event;
      const date = e.start === e.end ? e.start : `${e.start} → ${e.end}`;
      const topic = (lang === "en" ? e.topic_en : e.topic_zh) + (topicSubtag(e, lang) ? " · " + topicSubtag(e, lang) : "");
      const kwEn = lang === "en" ? splitKeywords(e.keywords_en).join(" / ") : "";
      const badges = w.badges.map((b) => tL(`badge_${b}`, lang)).join(", ");
      return `- **${date}** · ${topic} · ${e.headline}${kwEn ? ` · ${kwEn}` : ""}
  ${badges}`;
    })
    .join("\n");

  const upcomingRows = upcoming
    .map((e) => {
      const date = e.start === e.end ? e.start : `${e.start} → ${e.end}`;
      const topic = (lang === "en" ? e.topic_en : e.topic_zh) + (topicSubtag(e, lang) ? " · " + topicSubtag(e, lang) : "");
      const kwEn = lang === "en" ? splitKeywords(e.keywords_en).join(" / ") : "";
      return `- **${date}** · ${topic} · ${e.headline}${kwEn ? ` · ${kwEn}` : ""}`;
    })
    .join("\n");

  const title = tL("report_title", lang);
  const generated = tL("report_generated", lang);
  const disclaimer = tL("report_disclaimer", lang);
  const themeLabel = tL("monthlyTheme", lang);
  const signalHeader = tL("report_signal_header", lang);
  const signalColSignal = tL("report_signal_col_signal", lang);
  const signalColCount = tL("report_signal_col_count", lang);
  const signalColTrend = tL("report_signal_col_trend", lang);
  const watchlistHeader = tL("report_watchlist_header", lang);
  const upcomingHeader = tL("report_upcoming_header", lang);

  return `# ${title}

> ${generated}：${dateStr}

## ${themeLabel}

${lang === "en" ? theme.en : theme.zh}

## ${signalHeader}

| ${signalColSignal} | ${signalColCount} | ${signalColTrend} |
| --- | --- | --- |
${signalRows}

## ${watchlistHeader}

${watchlistRows || "-"}

## ${upcomingHeader}

${upcomingRows || "-"}

---

${disclaimer}
`;
}

function downloadMarkdown(filename, content) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportReport(events, y, m, lang) {
  const content = buildReport(events, y, m, lang);
  const suffix = `${y}-${String(m + 1).padStart(2, "0")}`;
  const filename = lang === "en" ? `Beijing-Events-Report-${suffix}-en.md` : `Beijing-Events-Report-${suffix}-zh.md`;
  downloadMarkdown(filename, content);
}

function exportBothReports(events, y, m) {
  exportReport(events, y, m, "zh");
  setTimeout(() => exportReport(events, y, m, "en"), 300);
}

/* ---- 事件悬停卡片（月历格子 .evt / 时间轴条形 .g-bar 共用）----
   position:fixed 挂 body，规避各视图滚动容器的 overflow 裁剪。
   元素需带 data-no；容器调 bindEventTip(container, selector) 绑定。 */
const _evtTip = document.createElement('div');
_evtTip.className = 'g-tip';
if (document.body) document.body.appendChild(_evtTip);
else document.addEventListener('DOMContentLoaded', () => document.body.appendChild(_evtTip));
let _evtTipAnchor = null;
function showEventTip(e, anchor) {
  if (!e) return;
  const lang = getLang();
  const multi = e.start !== e.end;
  const days = Math.round((stripTime(parseDate(e.end)) - stripTime(parseDate(e.start))) / DAY_MS) + 1;
  const sl = fmtDateL(parseDate(e.start), lang);
  const el2 = fmtDateL(parseDate(e.end), lang);
  const kws = splitKeywords(lang === 'en' ? e.keywords_en : e.keywords_zh);
  _evtTip.innerHTML =
    `<div class="tt-topic" data-topic="${e.topic_zh}"><span class="swatch"></span>${esc(topicName(e.topic_zh))}</div>` +
    `<div class="tt-head">${esc(e.headline)}</div>` +
    `<div class="tt-date">${esc(sl)}${multi ? ` -> ${esc(el2)} · ${days} ${t('dayUnit')}` : ''}</div>` +
    (kws.length ? `<div class="tt-kw">${kws.map(k => `<span class="k">${esc(k)}</span>`).join('')}</div>` : '');
  _evtTip.classList.add('show');
  const r = anchor.getBoundingClientRect();
  const tr = _evtTip.getBoundingClientRect();
  let left = r.left + r.width / 2 - tr.width / 2;
  let top = r.top - tr.height - 8;            /* 默认在元素上方 */
  if (top < 8) top = r.bottom + 8;            /* 上方放不下则翻到下方 */
  left = Math.max(8, Math.min(left, window.innerWidth - tr.width - 8));
  _evtTip.style.left = left + 'px';
  _evtTip.style.top = top + 'px';
}
function hideEventTip() { _evtTip.classList.remove('show'); _evtTipAnchor = null; }
function bindEventTip(container, selector) {
  if (!container) return;
  container.addEventListener('mouseover', ev => {
    const el = ev.target.closest(selector);
    if (!el || el === _evtTipAnchor) return;
    _evtTipAnchor = el;
    const e = (window.EVENTS || []).find(x => x.no === +el.dataset.no);
    if (e) showEventTip(e, el);
  });
  container.addEventListener('mouseout', ev => {
    const el = ev.target.closest(selector);
    if (!el) return;
    const rel = ev.relatedTarget;
    if (rel && el.contains(rel)) return;
    hideEventTip();
  });
}
/* 任何滚动（含嵌套滚动容器）都隐藏卡片，避免悬空错位 */
document.addEventListener('scroll', hideEventTip, true);

/* ===== 快速跳转：点击顶部年月标签展开「年+月」选择面板（3 视图共用）=====
   用法：mountMonthPicker({ getYM:()=>[y,m], setYM:(y,m)=>void, render:()=>void })
   data-topic / 颜色 key 仍用中文；这里只处理年月跳转，不触碰主题逻辑。 */
let _mpCSSInjected = false;
function _injectMpCSS() {
  if (_mpCSSInjected) return;
  _mpCSSInjected = true;
  const css = document.createElement('style');
  css.textContent =
    '.mp-panel{position:fixed;z-index:1100;background:var(--bg,#fff);border:1px solid var(--border,#e7e2dc);' +
    'border-radius:14px;box-shadow:0 20px 55px rgba(61,46,40,.2);padding:14px;width:248px;box-sizing:border-box;font-family:inherit;}' +
    '.mp-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}' +
    '.mp-y{border:none;background:transparent;cursor:pointer;color:var(--muted,#9a8f86);font-size:18px;width:30px;height:30px;' +
    'border-radius:8px;display:grid;place-items:center;transition:.15s;}' +
    '.mp-y:hover{background:var(--surface-2,#f0ece6);color:var(--text,#3d2e28);}' +
    '.mp-year{font-weight:800;font-size:16px;color:var(--text,#3d2e28);font-family:var(--font-display,inherit);}' +
    '.mp-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:10px;}' +
    '.mp-m{border:1px solid var(--border,#ece7e0);background:var(--surface,#faf8f5);border-radius:9px;padding:9px 0;' +
    'cursor:pointer;font-size:13px;color:var(--text,#3d2e28);transition:.15s;font-weight:600;}' +
    '.mp-m:hover{background:var(--primary,#c8553d);color:#fff;border-color:var(--primary,#c8553d);}' +
    '.mp-m.cur{background:var(--primary,#c8553d);color:#fff;border-color:var(--primary,#c8553d);}' +
    '.mp-today{width:100%;border:1px solid var(--border,#ece7e0);background:var(--surface,#faf8f5);border-radius:9px;' +
    'padding:8px;cursor:pointer;font-size:12px;color:var(--muted,#9a8f86);font-weight:700;transition:.15s;}' +
    '.mp-today:hover{background:var(--surface-2,#f0ece6);color:var(--text,#3d2e28);}' +
    '.mp-clickable{cursor:pointer;transition:color .15s;}' +
    '.mp-clickable:hover{color:var(--primary,#c8553d);}';
  document.head.appendChild(css);
}
function mountMonthPicker(opts) {
  const lbl = document.getElementById(opts.labelId || 'lbl');
  if (!lbl) return;
  _injectMpCSS();
  lbl.classList.add('mp-clickable');
  let panel = null, pickYear = null;
  const evs = window.EVENTS || [];
  let minYear = 9999, maxYear = 0;
  evs.forEach(e => { if (e && e.start) { const y = +String(e.start).slice(0, 4); if (y) { minYear = Math.min(minYear, y); maxYear = Math.max(maxYear, y); } } });
  if (!evs.length || minYear > maxYear) { const n = new Date(); minYear = maxYear = n.getFullYear(); }
  /* 前瞻 1 年：最大可选年 = max(数据最大年, 今天年份) + 1，方便预先规划未来年份（即使尚无事件） */
  maxYear = Math.max(maxYear, new Date().getFullYear()) + 1;
  function monthNames() {
    return getLang() === 'en'
      ? ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
      : ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  }
  function close() {
    if (panel) { panel.remove(); panel = null; }
    document.removeEventListener('mousedown', onOutside, true);
    document.removeEventListener('keydown', onKey, true);
  }
  function onOutside(ev) { if (panel && !panel.contains(ev.target) && ev.target !== lbl) close(); }
  function onKey(ev) {
    if (!panel) return;
    if (ev.key === 'Escape') { close(); }
    else if (ev.key === 'ArrowLeft') { ev.stopPropagation(); ev.preventDefault(); pickYear = Math.max(minYear, pickYear - 1); renderBody(); }
    else if (ev.key === 'ArrowRight') { ev.stopPropagation(); ev.preventDefault(); pickYear = Math.min(maxYear, pickYear + 1); renderBody(); }
  }
  function renderBody() {
    const en = getLang() === 'en';
    const cm = opts.getYM()[1];
    const cy = opts.getYM()[0];
    panel.innerHTML =
      '<div class="mp-head">' +
      '<button class="mp-y mp-prev" aria-label="' + (en ? 'Previous year' : '上一年') + '">‹</button>' +
      '<span class="mp-year">' + pickYear + '</span>' +
      '<button class="mp-y mp-next" aria-label="' + (en ? 'Next year' : '下一年') + '">›</button></div>' +
      '<div class="mp-grid">' + monthNames().map((nm, i) => {
        const cur = (i === cm && pickYear === cy) ? ' cur' : '';
        return '<button class="mp-m' + cur + '" data-m="' + i + '">' + nm + '</button>';
      }).join('') + '</div>' +
      '<button class="mp-today">' + (en ? 'Today' : '今天') + '</button>';
    panel.querySelector('.mp-prev').onclick = () => { pickYear = Math.max(minYear, pickYear - 1); renderBody(); };
    panel.querySelector('.mp-next').onclick = () => { pickYear = Math.min(maxYear, pickYear + 1); renderBody(); };
    panel.querySelectorAll('.mp-m').forEach(b => b.onclick = () => { opts.setYM(pickYear, +b.dataset.m); opts.render(); close(); });
    panel.querySelector('.mp-today').onclick = () => { const n = new Date(); opts.setYM(n.getFullYear(), n.getMonth()); opts.render(); close(); };
  }
  function open() {
    if (panel) return;
    pickYear = opts.getYM()[0];
    panel = document.createElement('div');
    panel.className = 'mp-panel';
    renderBody();
    document.body.appendChild(panel);
    const r = lbl.getBoundingClientRect();
    const pw = 248, gap = 6;
    let left = r.left + r.width / 2 - pw / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
    let top = r.bottom + gap;
    if (top + panel.offsetHeight > window.innerHeight - 8) top = Math.max(8, r.top - panel.offsetHeight - gap);
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
    document.addEventListener('mousedown', onOutside, true);
    document.addEventListener('keydown', onKey, true);
  }
  lbl.onclick = ev => { ev.stopPropagation(); if (panel) close(); else open(); };
}
