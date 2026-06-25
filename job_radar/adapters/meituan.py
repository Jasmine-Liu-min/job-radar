"""美团校园招聘（zhaopin.meituan.com，公开 JSON）。

接口（抓包发现）：
    POST https://zhaopin.meituan.com/api/official/job/getJobList
    body: {"page":{"pageNo":1,"pageSize":20},"jobShareType":"1","keywords":"","cityIdList":[],"jobTypeList":[]}
    返回 data.list[]：jobUnionId / name / cityList[{name}] / jobDuty / jobRequirement / desc / department
endpoint 仅记录根 URL。
"""
from __future__ import annotations

from typing import List

from ..models import RawJob
from . import register
from .http import post_json

_API = "https://zhaopin.meituan.com/api/official/job/getJobList"
PAGES = 10
PS = 20


@register("meituan")
def fetch(endpoint: str) -> List[RawJob]:
    jobs: List[RawJob] = []
    seen = set()
    for pg in range(1, PAGES + 1):
        body = {"page": {"pageNo": pg, "pageSize": PS}, "jobShareType": "1",
                "keywords": "", "cityIdList": [], "jobTypeList": []}
        try:
            d = post_json(_API, body, headers={"Referer": "https://campus.meituan.com/"})
        except Exception:  # noqa: BLE001
            break
        lst = ((d.get("data") or {}).get("list")) or []
        if not lst:
            break
        for m in lst:
            jid = m.get("jobUnionId")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            cities = "、".join(c.get("name", "") for c in (m.get("cityList") or [])
                              if isinstance(c, dict) and c.get("name"))
            jd = " ".join(str(x) for x in (m.get("jobDuty"), m.get("jobRequirement"),
                                           m.get("desc")) if x)[:2000]
            jobs.append(RawJob(
                company_name="美团",
                title=m.get("name", ""),
                location=cities,
                official_url=f"https://zhaopin.meituan.com/jobdetail?jobUnionId={jid}",
                jd_text=jd,
                raw={"platform": "meituan", "dept": m.get("department", ""), "needs_ai": False}))
        if len(lst) < PS:
            break
    return jobs
