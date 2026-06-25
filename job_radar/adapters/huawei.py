"""华为校园招聘（career.huawei.com，公开 JSON、无强反爬）。27届提前批主战场。

接口（抓包发现）：
    GET https://career.huawei.com/reccampportal/services/portal/portalpub/getJob/newHr/page/<pageSize>/<pageNum>?
    返回 {pageVO:{totalPages,...}, result:[{jobId,nameCn,jobCity,degree,releaseDate,expirationDate,
          mostlyDuty,demand,jobRequire,deptName,...}]}
endpoint 仅记录根 URL。
"""
from __future__ import annotations

from typing import List

from ..models import RawJob
from . import register
from .http import get_json

_API = "https://career.huawei.com/reccampportal/services/portal/portalpub/getJob/newHr/page/{ps}/{pg}?"
_REFERER = "https://career.huawei.com/reccampportal/portal5/campus-recruitment.html"
PAGES = 12
PS = 20


@register("huawei")
def fetch(endpoint: str) -> List[RawJob]:
    jobs: List[RawJob] = []
    seen = set()
    for pg in range(1, PAGES + 1):
        try:
            d = get_json(_API.format(ps=PS, pg=pg), headers={"Referer": _REFERER})
        except Exception:  # noqa: BLE001 — 翻页失败即停
            break
        res = d.get("result") or []
        if not res:
            break
        for r in res:
            jid = r.get("jobId")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            title = r.get("nameCn") or r.get("jobname") or r.get("externalJobName") or r.get("jobName") or ""
            loc = r.get("jobCity") or r.get("workPlace") or r.get("jobArea") or r.get("countryName") or ""
            jd = " ".join(str(x) for x in (r.get("mostlyDuty"), r.get("demand"),
                                           r.get("jobRequire")) if x)[:2000]
            jobs.append(RawJob(
                company_name="华为",
                title=str(title),
                location=str(loc),
                publish_time=str(r.get("releaseDate") or "")[:10],
                deadline=str(r.get("expirationDate") or "")[:10],
                official_url=f"https://career.huawei.com/reccampportal/portal5/campus-recruitment-detail.html?jobId={jid}",
                jd_text=jd,
                raw={"platform": "huawei", "degree": r.get("degree", ""),
                     "dept": r.get("deptName", ""), "needs_ai": False}))
        pv = d.get("pageVO") or {}
        try:
            if pg >= int(pv.get("totalPages", pg)):
                break
        except (TypeError, ValueError):
            pass
    return jobs
