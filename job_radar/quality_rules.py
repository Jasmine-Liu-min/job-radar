"""岗位质量标签与默认降噪规则。

质量标签不删除数据，只帮助工作台默认隐藏明显低质项，并允许用户单独查看。
"""
from __future__ import annotations

from typing import List, Tuple

LOW_QUALITY_TAGS = {
    "代招/委托",
    "猎头",
    "劳务派遣",
    "泛销售",
    "低相关管培",
    "地点风险",
    "缺官网链接",
}

_AGENCY_KW = ("代招", "外包", "第三方", "人力资源管理有限公司", "人才服务有限公司", "劳务")
_AGENCY_TITLE_KW = ("委托单位", "委托招聘", "代招", "外包", "第三方")
_HEADHUNT_KW = ("猎头", "headhunter", "猎聘")
_DISPATCH_KW = ("劳务派遣", "派遣")
_SALES_KW = ("销售代表", "销售专员", "客户经理", "电话销售", "渠道销售", "招商", "地推", "电销")
_MANAGEMENT_TRAINEE_KW = ("管培", "管理培训生", "储备干部", "储备生")
_TARGET_KW = (
    "数据", "算法", "机器学习", "数据科学", "数据挖掘", "产品", "战略", "经营分析",
    "商业分析", "行业研究", "数字化", "ai", "大模型", "统计", "量化", "风控",
)
_REMOTE_BAD_KW = ("县", "乡", "镇")


def quality_tags(job) -> Tuple[List[str], List[str]]:
    """返回 (quality_tags, risk_flags)。job 可以是 Job 或含同名字段的对象。"""
    title = getattr(job, "title", "") or ""
    company = getattr(job, "company_name", "") or ""
    jd = getattr(job, "jd_text", "") or ""
    loc = getattr(job, "location", "") or ""
    url = getattr(job, "official_url", "") or ""
    deadline = getattr(job, "deadline", "") or ""
    sid = getattr(job, "source_id", "") or ""
    text = f"{title} {company} {jd}".lower()
    title_low = title.lower()

    tags: List[str] = []
    risks: List[str] = []
    agency_text = f"{title} {company}".lower()
    if any(k.lower() in agency_text for k in _AGENCY_KW) or any(k in title for k in _AGENCY_TITLE_KW):
        tags.append("代招/委托")
    if any(k.lower() in text for k in _HEADHUNT_KW):
        tags.append("猎头")
    if any(k in text for k in _DISPATCH_KW):
        tags.append("劳务派遣")
        risks.append("劳务派遣")
    if any(k in title for k in _SALES_KW):
        tags.append("泛销售")
    if any(k in title for k in _MANAGEMENT_TRAINEE_KW) and not any(k.lower() in text for k in _TARGET_KW):
        tags.append("低相关管培")
    if not deadline:
        tags.append("缺截止")
    if not url:
        tags.append("缺官网链接")
    if sid in ("cn-bytedance", "cn-tencent", "cn-jd") or sid.startswith("wd-"):
        tags.append("仅社招")
    if any(k in loc for k in _REMOTE_BAD_KW):
        tags.append("地点风险")
    return list(dict.fromkeys(tags)), list(dict.fromkeys(risks))


def is_low_quality(tags: List[str]) -> bool:
    return bool(LOW_QUALITY_TAGS & set(tags or []))
