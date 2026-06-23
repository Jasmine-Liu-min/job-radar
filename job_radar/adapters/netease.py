"""网易招聘官网接口（hr.163.com，公开 JSON、无强反爬）。

接口（通过抓包发现）：
    POST https://hr.163.com/api/hr163/position/queryPage
    body(JSON): {"currentPage":1,"pageSize":20,"workType":"","firstType":"","keyword":""}
    返回 data.list[]：name 职位 / workPlaceList 地点 / firstPostTypeName 职类 /
        requirement+description JD / reqEducationName 学历 / recruitNum 招聘数 / id

网易以游戏为主（互娱/雷火），含数据/算法/后端/游戏AI 等对口岗，亦有实习生/校招。
endpoint 仅记录根 URL。
"""
from __future__ import annotations

from typing import List

from ..models import RawJob
from . import register
from .http import post_json

_API = "https://hr.163.com/api/hr163/position/queryPage"
PAGES = 6
PAGE = 20


def _loc(wp) -> str:
    if not wp:
        return ""
    if isinstance(wp, list):
        names = []
        for w in wp:
            if isinstance(w, dict):
                names.append(w.get("name") or w.get("workPlaceName") or "")
            else:
                names.append(str(w))
        return "、".join(n for n in names if n)
    return str(wp)


@register("netease")
def fetch(endpoint: str) -> List[RawJob]:
    jobs: List[RawJob] = []
    seen = set()
    for p in range(1, PAGES + 1):
        body = {"currentPage": p, "pageSize": PAGE, "workType": "",
                "firstType": "", "secondType": "", "keyword": ""}
        try:
            d = post_json(_API, body, headers={"Referer": "https://hr.163.com/job-list.html"})
        except Exception:  # noqa: BLE001 — 翻页失败即停
            break
        lst = (d.get("data") or {}).get("list") or []
        if not lst:
            break
        for e in lst:
            jid = e.get("id")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            jd = " ".join(filter(None, [e.get("requirement", ""), e.get("description", "")]))[:2000]
            jobs.append(RawJob(
                company_name="网易",
                title=e.get("name", ""),
                location=_loc(e.get("workPlaceNameList") or e.get("workPlaceList")),
                publish_time=str(e.get("updateTime", ""))[:10] if e.get("updateTime") else "",
                official_url=f"https://hr.163.com/job-detail.html?positionId={jid}",
                jd_text=jd,
                raw={"platform": "netease", "degree": e.get("reqEducationName", ""),
                     "postType": e.get("firstPostTypeName", ""), "needs_ai": False}))
        if len(lst) < PAGE:
            break
    return jobs
