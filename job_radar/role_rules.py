"""岗位方向与雇主层级规则。

这里集中维护会频繁变化的"求职方向"口径：
- 数据/算法/机器学习
- 产品/AI 产品/策略产品
- 决策支持/经营战略
- 雇主层级（央国企/大厂/硬科技/外企）

score.py 只负责把这些规则组装成最终分数，避免评分主流程变成关键词仓库。
"""
from __future__ import annotations

from typing import List, Tuple


TARGET_ROLE_SIGNAL = (
    "数据", "统计", "算法", "数据分析", "商业分析", "数据挖掘", "建模", "机器学习",
    "深度学习", "数据科学", "量化", "风控", "数仓", "数据仓库", "etl", "大数据",
    "nlp", "自然语言", "计算机视觉", "cv算法", "推荐算法", "后端", "软件开发",
    "数据开发", "测试开发", "python", "java", "golang", "人工智能", "大模型", "llm",
    "analyst", "scientist", "machine learning", "data ", "数据分析师",
    "产品", "产品经理", "产品策划", "产品运营", "产品分析", "需求分析", "需求管理",
    "策略产品", "ai产品", "aigc产品", "大模型产品", "智能体产品", "数据产品",
    "平台产品", "商业产品", "增长产品", "用户增长", "用户研究", "产品设计",
    "product manager", "product analyst", "product owner", "pm",
    "战略", "战略分析", "战略规划", "经营分析", "经营管理", "商业分析", "行业研究",
    "产业研究", "市场研究", "竞品分析", "投研", "投资分析", "总裁办", "ceo office",
    "董办", "管培", "管理培训生", "项目管理", "pmo", "数字化转型", "管理咨询",
    "业务分析", "决策支持",
)

PRODUCT_ROLE_SIGNAL = (
    "产品", "产品经理", "产品策划", "产品运营", "产品分析", "需求分析", "需求管理",
    "策略产品", "ai产品", "aigc产品", "大模型产品", "智能体产品", "数据产品",
    "平台产品", "商业产品", "增长产品", "用户增长", "用户研究", "产品设计",
    "product manager", "product analyst", "product owner",
)
AI_PRODUCT_SIGNAL = ("ai产品", "aigc产品", "大模型产品", "智能体产品", "人工智能产品", "agent产品")
STRATEGY_PRODUCT_SIGNAL = ("策略产品", "策略", "推荐策略", "搜索策略", "供需策略", "交易策略", "定价策略")
ALGO_ML_SIGNAL = (
    "算法", "机器学习", "深度学习", "推荐算法", "搜索算法", "广告算法", "排序模型",
    "召回", "ctr", "cvr", "nlp", "自然语言", "计算机视觉", "cv算法", "大模型算法",
    "llm", "多模态", "强化学习", "模型训练", "模型评估", "特征工程", "ai算法",
)
DATA_SCIENCE_SIGNAL = (
    "数据科学", "数据科学家", "data scientist", "数据建模", "统计建模", "实验设计",
    "因果推断", "ab实验", "a/b", "商业分析", "数据分析", "数据分析师", "analytics",
)
DATA_MINING_SIGNAL = (
    "数据挖掘", "用户画像", "画像建模", "知识图谱", "异常检测", "风控建模",
    "反作弊", "反欺诈", "预测模型", "挖掘算法",
)
DECISION_SIGNAL = (
    "战略", "战略分析", "战略规划", "经营分析", "经营管理", "商业分析", "商业分析师",
    "行业研究", "产业研究", "市场研究", "竞品分析", "商业模式", "投研", "投资分析",
    "总裁办", "ceo office", "董办", "管培", "管理培训生", "项目管理", "pmo",
    "数字化转型", "管理咨询", "流程优化", "业务分析", "决策支持", "解决方案",
)
DECISION_DROP = ("销售", "销售代表", "客户经理", "招商主管", "招商经理", "电话", "客服", "渠道销售")

BIGTECH = ("腾讯", "字节", "抖音", "阿里", "蚂蚁", "美团", "京东", "百度", "快手",
           "网易", "滴滴", "拼多多", "小米", "华为", "哔哩哔哩", "小红书", "携程",
           "微博", "vivo", "oppo", "顺丰")
HARDTECH_CO = ("商汤", "地平线", "旷视", "云从", "依图", "寒武纪", "黑芝麻", "壁仞",
               "摩尔线程", "燧原", "比亚迪", "宁德时代", "蔚来", "理想汽车", "小鹏",
               "大疆", "中芯", "海光", "华大")
SOE_KW = ("中国", "国家电网", "南方电网", "中核", "中船", "中航", "航空工业", "航发",
          "中国电子", "中国电科", "中电科", "中铁", "中建", "中交", "中粮", "中化",
          "中石油", "中石化", "中海油", "华能", "大唐", "国家能源", "国电投",
          "中国移动", "中国电信", "中国联通", "国投", "中信", "华润", "招商局",
          "中广核", "中国华电", "中国能建", "中国电建", "中煤", "中国邮政")
HARD_IND = ("半导体/电子", "航空航天/军工", "新材料", "汽车/新能源车", "能源/电力/石化")


def has_target_role_signal(title: str) -> bool:
    low = (title or "").lower()
    return any(k in low for k in TARGET_ROLE_SIGNAL)


def role_signal_score(title: str, jd_text: str) -> Tuple[int, List[str]]:
    title_low = (title or "").lower()
    text_low = f"{title or ''} {jd_text or ''}".lower()
    score = 0
    tags: List[str] = []

    if any(k in title_low for k in PRODUCT_ROLE_SIGNAL):
        score += 22
        tags.append("产品")
    if any(k in text_low for k in AI_PRODUCT_SIGNAL):
        score += 10
        tags.append("AI产品")
    if any(k in text_low for k in STRATEGY_PRODUCT_SIGNAL):
        score += 8
        tags.append("策略产品")
    if any(k in text_low for k in ALGO_ML_SIGNAL):
        score += 22
        tags.append("算法/ML")
    if any(k in text_low for k in DATA_SCIENCE_SIGNAL):
        score += 20
        tags.append("数据科学")
    if any(k in text_low for k in DATA_MINING_SIGNAL):
        score += 18
        tags.append("数据挖掘")
    if any(k in text_low for k in DECISION_SIGNAL) and not any(k in title_low for k in DECISION_DROP):
        score += 18
        tags.append("决策支持")
    return score, list(dict.fromkeys(tags))


def employer_tier(company: str, industry: str, sid: str) -> Tuple[str, int]:
    """据公司名(+行业/信源)判雇主层级 → (标签, 加分)。"""
    c = company or ""
    if any(b in c for b in BIGTECH):
        return "大厂", 28
    if any(b in c for b in HARDTECH_CO):
        return "硬科技", 28
    if sid.startswith(("wd-", "gh-", "ashby-", "lever-")):
        return "外企", 22
    if any(k in c for k in SOE_KW) or sid in ("gov-sasac", "gov-qyzp", "cn-iguopin"):
        return "央国企", 30
    if industry in HARD_IND and not sid.startswith(("edu-", "gov-")):
        return "硬科技", 18
    return "", 0
