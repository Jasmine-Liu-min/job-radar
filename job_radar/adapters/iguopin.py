"""国聘（iguopin.com）公开职位接口。

国聘是央国企/国企岗位的重要聚合源。React 首页本身只有壳，但公开 API 可直接查询：
    POST https://gp-api.iguopin.com/api/jobs/v1/list

本 adapter 先按 27届/校招/提前批/数据/算法/实习等关键词多路搜索，保守抓取
与用户画像更相关的岗位，并保留 end_time 作为 deadline。
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List

from ..models import RawJob
from ..keyword_config import iguopin_keywords
from . import register
from .http import post_json

_API = "https://gp-api.iguopin.com/api/jobs/v1/list"
_HEADERS = {"Referer": "https://www.iguopin.com/", "Origin": "https://www.iguopin.com"}
MAX_RESULTS = 240
_KEEP = re.compile(
    r"(2027|27届|提前批|校招|校园招聘|实习|数据|算法|AI|人工智能|大模型|机器学习|统计|量化|风控|"
    r"数据科学|数据挖掘|深度学习|推荐算法|搜索算法|NLP|CV|LLM|多模态|"
    r"产品|策略|需求|增长|用户|商业化|平台|AIGC|智能体|"
    r"战略|经营|商业分析|行业研究|产业研究|投研|投资分析|总裁办|管培|项目管理|数字化转型|决策|"
    r"中国|国家|国投|中铁|中建|中交|中电|中航|航天|航空|央企|国企)"
)
_DROP = re.compile(r"(司机|保安|保洁|服务员|厨师|普工|操作工|销售代表|电话客服|主播|房产|置业)")


def _date(v) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    return s[:10]


def _salary(e: Dict) -> str:
    if e.get("is_negotiable"):
        return ""
    lo, hi = e.get("min_wage") or 0, e.get("max_wage") or 0
    if not lo and not hi:
        return ""
    unit = e.get("wage_unit_cn") or ""
    months = e.get("months")
    extra = f"·{months}薪" if months and str(months) != "12" else ""
    return f"{lo or '?'}-{hi or '?'}{unit}{extra}"


def _location(e: Dict) -> str:
    names = []
    for d in e.get("district_list") or []:
        name = d.get("city_name") or d.get("area_cn") or d.get("province_name") or d.get("name")
        if name and name not in names:
            names.append(name)
    return " / ".join(names[:3])


def _iter_jobs(keyword: str) -> Iterable[Dict]:
    for page in range(1, 2):
        body = {"page": page, "page_size": 50, "keyword": keyword}
        try:
            data = post_json(_API, body, headers=_HEADERS, timeout=5)
        except Exception:  # noqa: BLE001 — 单关键词/单页失败不拖垮整源
            break
        payload = data.get("data") or {}
        rows = payload.get("list") or []
        if not rows:
            break
        yield from rows
        if len(rows) < 20:
            break


@register("iguopin")
def fetch(endpoint: str) -> List[RawJob]:
    out: List[RawJob] = []
    seen = set()
    for kw in iguopin_keywords():
        for e in _iter_jobs(kw):
            jid = str(e.get("job_id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            title = e.get("job_name") or ""
            company = e.get("company_name") or "国聘"
            blob = " ".join(filter(None, [
                title, company, e.get("recruitment_type_cn"), e.get("nature_cn"),
                e.get("category_cn"), e.get("education_cn"), e.get("experience_cn"),
            ]))
            if _DROP.search(blob) or not _KEEP.search(blob):
                continue
            jd = " · ".join(filter(None, [
                e.get("recruitment_type_cn"), e.get("nature_cn"), e.get("category_cn"),
                e.get("education_cn"), e.get("experience_cn"), _salary(e),
            ]))
            out.append(RawJob(
                company_name=company,
                title=title,
                location=_location(e),
                publish_time=_date(e.get("start_time") or e.get("create_time")),
                deadline=_date(e.get("end_time")),
                official_url=f"https://www.iguopin.com/job/detail?id={jid}",
                jd_text=jd,
                raw={"platform": "iguopin", "salary": _salary(e),
                     "recruitment_type": e.get("recruitment_type_cn", ""),
                     "nature": e.get("nature_cn", ""), "category": e.get("category_cn", ""),
                    "needs_ai": False},
            ))
            if len(out) >= MAX_RESULTS:
                return out
    return out
