"""北森(Beisen)招聘 ATS 通用 adapter（国内通用，纯 HTTP 无签名）。

大量国内硬科技/制造公司用北森招聘(域名 *.hotjob.cn / *.zhiye.com / 企业 hr 子域)，
职位接口公开、无签名，直连即可：
    POST https://<host>/wecruit/positionInfo/listPosition/<SU_id>
    body(form): isFrompb=true&recruitType=<1校园|2社招>&pageSize=20&currentPage=<n>

已验证：商汤 hr.sensetime.com|SU60fa…、地平线 wecruit.hotjob.cn|SU6409…
endpoint 用竖线分隔：host|SU_id。公司中文名由 config/sources.csv company_name 列兜底。

字段：postName 职位 / workPlaceStr 地点 / publishDate 发布 / endDate 截止 /
      educationStr 学历 / recruitNumStr 招聘数 / projectName 项目 / postId 详情。
"""
from __future__ import annotations

import time
from typing import List

from ..models import RawJob
from . import register
from .http import post_form

MAX_PAGES = 5
PAGE = 20


def _call(host: str, su: str, recruit_type: int, page: int):
    ts = int(time.time() * 1000)
    url = (f"https://{host}/wecruit/positionInfo/listPosition/{su}"
           f"?iSaJAx=isAjax&request_locale=zh_CN&t={ts}")
    body = {"isFrompb": "true", "recruitType": recruit_type,
            "pageSize": PAGE, "currentPage": page}
    return post_form(url, body, headers={"Referer": f"https://{host}/{su}/pb/"})


@register("beisen")
def fetch(endpoint: str) -> List[RawJob]:
    try:
        host, su = endpoint.split("|", 1)
    except ValueError:
        raise RuntimeError("beisen endpoint 需为 host|SU_id 格式")

    jobs: List[RawJob] = []
    seen = set()
    for rt in (1, 2):                      # 1=校园招聘，2=社会招聘
        for page in range(1, MAX_PAGES + 1):
            try:
                d = _call(host, su, rt, page)
            except Exception:              # noqa: BLE001 — 单类/单页失败不影响其它
                break
            pf = (d.get("data") or {}).get("pageForm") or {}
            posts = pf.get("pageData") or []
            if not posts:
                break
            for p in posts:
                pid = str(p.get("postId") or p.get("postCode") or "")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                jd = " · ".join(filter(None, [
                    p.get("postTypeName", ""), p.get("educationStr", ""),
                    p.get("recruitNumStr", ""), p.get("projectName", ""),
                ]))
                jobs.append(RawJob(
                    company_name="",       # CSV company_name 兜底
                    title=p.get("postName", ""),
                    location=p.get("workPlaceStr", ""),
                    publish_time=(p.get("publishDate") or "")[:10],
                    deadline=(p.get("endDate") or "")[:10],
                    official_url=f"https://{host}/{su}/pb/posDetail.html?postId={pid}",
                    jd_text=jd,
                    raw={"platform": "beisen", "id": pid},
                ))
            if page >= int(pf.get("totalPage") or 1):
                break
    return jobs
