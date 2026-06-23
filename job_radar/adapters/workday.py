"""Workday ATS 通用 adapter（在华外企，公开 cxs JSON 接口）。

大量跨国公司(英伟达/3M/戴尔/施耐德等)用 Workday 托管招聘，接口公开、无强反爬：
    POST https://<host>/wday/cxs/<tenant>/<site>/jobs
本 adapter 面向"在华外企"——自动从 facets 里定位"中国/China"地点筛子，只取在华岗位
（国内可投，且多为大厂之外、更可投的多元雇主）。

endpoint 用竖线分隔：host|tenant|site
    例：nvidia.wd5.myworkdayjobs.com|nvidia|NVIDIAExternalCareerSite

Workday 列表无 JD 正文（需进详情页），故 jd 暂留标题；地点取 locationsText。
"""
from __future__ import annotations

import re
from typing import List

from ..models import RawJob
from . import register
from .http import post_json

PAGES = 3
PAGE = 20
_CN = re.compile(r"(China|中国|Shanghai|Beijing|Shenzhen|Suzhou|Guangzhou|Chengdu|Hangzhou|"
                 r"Wuhan|Xi'an|上海|北京|深圳|苏州|广州|成都|杭州|武汉|Hong Kong|香港)", re.I)


def _post(host, tenant, site, body):
    url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    return post_json(url, body, headers={"Referer": f"https://{host}/"})


def _find_china_facet(data):
    """从 facets 里找"中国/China"的 (facetParameter, id)。"""
    for f in data.get("facets", []):
        param = f.get("facetParameter", "")
        for v in f.get("values", []):
            if re.search(r"China|中国", str(v.get("descriptor", "")), re.I):
                return param, v.get("id")
    return None, None


@register("workday")
def fetch(endpoint: str) -> List[RawJob]:
    try:
        host, tenant, site = endpoint.split("|", 2)
    except ValueError:
        raise RuntimeError("workday endpoint 需为 host|tenant|site 格式")

    # 1) 先读 facets，定位中国地点筛子
    probe = _post(host, tenant, site, {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
    param, cid = _find_china_facet(probe)
    applied = {param: [cid]} if cid else {}

    jobs: List[RawJob] = []
    seen = set()
    for page in range(PAGES):
        body = {"appliedFacets": applied, "limit": PAGE, "offset": page * PAGE, "searchText": ""}
        try:
            d = _post(host, tenant, site, body)
        except Exception:  # noqa: BLE001
            break
        posts = d.get("jobPostings", [])
        if not posts:
            break
        for p in posts:
            loc = p.get("locationsText", "") or ""
            # facet 没定位到时，用地点关键词兜底过滤在华岗位
            if not cid and not _CN.search(loc):
                continue
            path = p.get("externalPath", "")
            url = f"https://{host}/en-US/{site}{path}" if path else f"https://{host}/"
            if url in seen:
                continue
            seen.add(url)
            jobs.append(RawJob(
                company_name="",   # 由 config/sources.csv company_name 兜底
                title=p.get("title", ""),
                location=loc,
                official_url=url,
                jd_text=p.get("title", ""),
                raw={"platform": "workday", "needs_ai": True},
            ))
        if (page + 1) * PAGE >= d.get("total", 0):
            break
    return jobs
