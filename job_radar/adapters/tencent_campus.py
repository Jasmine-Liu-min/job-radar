"""腾讯校园招聘门户 join.qq.com（校招/实习，比 careers 社招接口全得多）。

社招接口（tencent adapter）只给社会招聘；应届校招与实习在独立门户 join.qq.com，
公开 JSON 接口、无强反爬：
    POST https://join.qq.com/api/v1/position/searchPosition
    body 翻页，返回 data.positionList[]（postId/positionTitle/workCities/recruitLabelName），data.count 总数

recruitLabelName 标识"应届实习"等类型，据此把标题标注（含"实习"则进实习 Tab）。
详情页用 careers.tencent.com/jobdesc.html?postId= 拼（已知有效格式）。
"""
from __future__ import annotations

from typing import List

from ..models import RawJob
from . import register
from .http import post_json

_API = "https://join.qq.com/api/v1/position/searchPosition"
PAGE = 100
MAX_PAGES = 8


@register("tencent_campus")
def fetch(endpoint: str) -> List[RawJob]:
    jobs: List[RawJob] = []
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        body = {"keyword": "", "pageIndex": page, "pageSize": PAGE,
                "bgIds": [], "productIds": [], "categoryIds": [],
                "workLocationIds": [], "projectType": ""}
        try:
            d = post_json(_API, body, headers={"Referer": "https://join.qq.com/"})
        except Exception:  # noqa: BLE001 — 翻页失败即停，已抓到的保留
            break
        data = d.get("data") or {}
        lst = data.get("positionList") or []
        if not lst:
            break
        for p in lst:
            pid = p.get("postId") or p.get("id")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            label = p.get("recruitLabelName") or p.get("projectName") or ""
            title = p.get("positionTitle") or ""
            if label and label not in title:
                title = f"{title}（{label}）"   # 标注 应届实习/校招 类型，实习据此进实习 Tab
            cities = (p.get("workCities") or "").split()
            jobs.append(RawJob(
                company_name="腾讯",
                title=title,
                location=cities[0] if cities else "",
                official_url=f"https://careers.tencent.com/jobdesc.html?postId={pid}",
                jd_text=" · ".join(filter(None, [
                    p.get("positionTitle"), label, p.get("bgs"), p.get("workCities")]))[:800],
                raw={"platform": "tencent_campus", "label": label,
                     "employmentType": "INTERN" if "实习" in label else "",
                     "needs_ai": False},
            ))
        if len(seen) >= data.get("count", 0) or len(lst) < PAGE:
            break
    return jobs
