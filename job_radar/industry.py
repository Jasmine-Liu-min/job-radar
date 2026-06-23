"""行业分类器（规则制、零成本、可解释）。

按"公司名 + 职位"做匹配（**不用 JD 全文**——JD 里的福利样板如 health/medical
insurance、fund/capital 等会严重污染分类）。两道判据：
1. 品牌映射表 BRANDS：海外 ATS 的 company 是 token（如 databricks/stripe），直接查表最准；
2. 关键词规则 INDUSTRY_RULES：中文用子串、英文用词边界（避免 soc/ic/ai 子串误命中）。

规则顺序 = 优先级：先具体行业、后宽泛，避免"互联网/软件"吃掉半导体/金融等。
"""
from __future__ import annotations

import re

# 海外 ATS 公司 token → 行业（最可靠，优先查）
BRANDS = {
    "互联网/软件": ["databricks", "anthropic", "openai", "figma", "gitlab", "posthog",
                "airtable", "notion", "canva", "retool", "linear", "palantir", "vanta"],
    "半导体/电子": ["英伟达", "nvidia", "应用材料", "applied materials", "amat", "高通", "qualcomm",
                "中芯", "海光", "amd", "地平线", "horizon", "寒武纪", "黑芝麻",
                "英特尔", "恩智浦", "nxp", "科磊", "kla", "美光", "micron", "德州仪器",
                "意法半导体", "stmicro", "英飞凌", "infineon", "亚德诺", "microchip", "安森美"],
    "先进制造/工业": ["3m", "西门子", "施耐德", "霍尼韦尔", "abb", "博世", "通用电气"],
    "金融": ["stripe", "ramp", "brex", "affirm", "chime", "sofi", "robinhood",
            "coinbase", "plaid"],
    "消费/零售/快消": ["instacart", "doordash", "gopuff", "nike"],
    "医疗/医药": ["komodohealth", "tempus", "benchling", "moderna",
              "辉瑞", "pfizer", "强生", "罗氏", "拜耳", "默沙东", "阿斯利康", "诺华",
              "雅培", "abbott", "美敦力", "medtronic", "西门子医疗", "丹纳赫", "赛默飞"],
    "汽车/新能源车": ["lucidmotors", "rivian", "cruise"],
    "传媒/文娱/广告": ["spotify"],
}
_BRAND_LOOKUP = {b: ind for ind, bs in BRANDS.items() for b in bs}

# (行业, [中文关键词...], [英文关键词(词边界匹配)...])，越靠前优先级越高
INDUSTRY_RULES = [
    ("半导体/电子", ["半导体", "芯片", "集成电路", "晶圆", "封测", "光刻", "射频", "存储芯片",
        "中芯", "海光", "寒武纪", "韦尔", "兆易", "长鑫", "长江存储", "格见", "炬光", "韶音"],
        ["semiconductor", "wafer", "asic", "fpga", "chip"]),
    ("新材料", ["新材料", "碳纤维", "正极材料", "负极材料", "隔膜", "电解液", "光刻胶",
        "半导体材料", "电子材料", "磁性材料", "石墨烯", "复合材料", "特种材料", "高分子材料",
        "锂电材料", "容百", "当升", "璞泰来", "恩捷", "雅克科技", "中复神鹰"], []),
    ("汽车/新能源车", ["汽车", "整车", "新能源车", "动力电池", "电芯", "充电桩", "自动驾驶",
        "比亚迪", "宁德时代", "蔚来", "理想汽车", "小鹏", "广汽", "上汽", "一汽", "吉利", "长城汽车"],
        ["automotive"]),
    ("金融", ["银行", "保险", "证券", "基金", "信托", "支付", "金融", "投行", "资管", "财富管理",
        "工商银行", "建设银行", "招商银行", "中国银行", "平安", "蚂蚁", "微众", "陆金所"],
        ["fintech", "payment", "insurance", "brokerage"]),
    ("医疗/医药", ["医药", "制药", "生物科技", "医疗", "临床", "医院", "诊断", "疫苗", "医疗器械",
        "药明", "恒瑞", "百济", "迈瑞", "联影"],
        ["pharma", "biotech", "clinical"]),
    ("能源/电力/石化", ["电网", "电力", "发电", "能源", "石油", "石化", "天然气", "核电", "风电", "光伏",
        "国家电网", "南方电网", "中石油", "中石化", "中海油", "华能", "大唐", "国家能源"], []),
    ("航空航天/军工", ["航空", "航天", "卫星", "兵器", "军工", "国防", "船舶", "导弹", "雷达",
        "航发", "商飞", "航空工业", "中航", "部队", "军事"], ["aerospace", "defense"]),
    ("通信", ["通信", "运营商", "基站", "光通信", "中国移动", "中国电信", "中国联通", "华为", "中兴"],
        ["telecom"]),
    ("先进制造/工业", ["制造", "机械", "装备", "重工", "钢铁", "机床", "工业自动化", "机器人", "精密",
        "三一", "中联重科", "格力", "美的", "海尔", "立讯", "富士康"],
        ["manufacturing", "robotics", "machinery"]),
    ("消费/零售/快消", ["零售", "快消", "食品", "饮料", "服饰", "电商", "美妆", "连锁", "餐饮",
        "宝洁", "联合利华", "欧莱雅", "可口可乐", "百胜", "星巴克", "安踏", "李宁"],
        ["retail", "fmcg", "ecommerce"]),
    ("房地产/建筑/工程", ["房地产", "地产", "建筑", "施工", "设计院", "勘察", "基建", "中建",
        "中铁", "中交", "保利", "万科"], ["construction"]),
    ("物流/交通", ["物流", "供应链", "快递", "仓储", "货运", "港口", "航运", "顺丰"],
        ["logistics", "freight"]),
    ("传媒/文娱/广告", ["传媒", "影视", "游戏", "广告", "营销", "文娱", "直播", "短视频", "出版"],
        ["advertising", "entertainment"]),
    ("化工", ["化工", "化学", "涂料", "塑料", "橡胶", "化肥", "农药", "石化", "炼化"], ["chemical"]),
    ("教育/科研", ["教育", "培训", "研究院", "研究所", "实验室"], ["education", "institute"]),
    ("咨询/专业服务", ["咨询", "会计师", "律师", "审计", "猎头"], ["consulting", "advisory"]),
    ("政府/事业单位", ["事业单位", "政府", "机关", "公务员", "选调", "街道", "社区", "人社", "管委会"], []),
    ("互联网/软件", ["互联网", "软件", "云计算", "大数据", "人工智能", "大模型", "算法工程师",
        "字节", "腾讯", "阿里", "美团", "京东", "百度", "快手", "网易", "滴滴", "拼多多"],
        ["software", "machine learning", "data platform", "saas"]),
]

# 预编译：每条规则 = (行业, 中文关键词, 英文词边界正则|None)，保持优先级顺序
_RULES = [(ind, zh,
           re.compile(r"\b(" + "|".join(re.escape(k) for k in en) + r")\b") if en else None)
          for ind, zh, en in INDUSTRY_RULES]
# 仅对"源即雇主"的类型做兜底（ATS/大厂官网）；聚合平台(public_institution/soe/research)
# 的 org_type 是平台属性而非雇主行业，兜底会误判，故归"其他"，由关键词决定。
_ORG_FALLBACK = {"finance": "金融", "internet": "互联网/软件", "tech": "互联网/软件"}


def classify(company_name: str, title: str = "", jd_text: str = "", org_type: str = "") -> str:
    """返回行业名（粗分类）。仅用 公司名 + 职位（不用 JD，避免样板词污染）。"""
    comp = (company_name or "").lower()
    for brand, ind in _BRAND_LOOKUP.items():
        if brand in comp:
            return ind
    text = f"{company_name} {title}".lower()
    for ind, zh, rgx in _RULES:        # 按优先级逐行业，中英一起判
        if any(k in text for k in zh) or (rgx and rgx.search(text)):
            return ind
    return _ORG_FALLBACK.get(org_type, "其他")
