"""国家大学生就业服务平台 / 24365（P3 国家级官方聚合平台）。

教育部学生服务与素质发展中心主办的全国高校毕业生就业平台（ncss.cn / 24365），
面向应届生校招，覆盖全国、含国企/机关事业单位/重点领域。其职位列表是公开 JSON
接口、**无反爬**，直接 urllib 即可：

    https://www.ncss.cn/student/jobs/jobslist/ajax/?offset=<page>&limit=<n>&...

返回 data.list[]，字段含：
    jobName 职位名 / recName 招聘单位 / lowMonthPay-highMonthPay 月薪(K)
    areaCodeName 地区 / degreeName 学历 / major 专业 / headCount 招聘人数
    recProperty 单位性质 / recScale 规模 / publishDate 发布(epoch ms)
    jobId/recId 详情 id / sourcesNameCh 来源

接口支持丰富筛选参数（areaCode 地区 / degreeCode 学历 / recruitType 校招类型 /
categoryCode 职类），后续可按画像下推过滤。本 adapter 先抓最新若干页。

注意：平台聚合多来源，混有兼职/低质岗位，交由打分与风险层(score.py)降权。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from ..models import RawJob
from . import register
from .http import get_json

PAGES = 8       # 抓取页数（国家级聚合源，加深以提量）
PAGE_SIZE = 30  # 每页条数


def _base(endpoint: str) -> str:
    """endpoint 支持 www.ncss.cn（全国）/ shixi.ncss.cn（教育部实习平台）等同构子站。"""
    return endpoint.rstrip("/") if (endpoint or "").startswith("http") else "https://www.ncss.cn"


def _date(ms) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def _salary(e: dict) -> str:
    lo, hi = e.get("lowMonthPay"), e.get("highMonthPay")
    if lo or hi:
        return f"{lo or '?'}-{hi or '?'}K/月"
    return ""


@register("ncss")
def fetch(endpoint: str) -> List[RawJob]:
    base = _base(endpoint)
    ajax = base + "/student/jobs/jobslist/ajax/"
    detail = base + "/student/jobs/jobsdetail/index.html?jobId="
    headers = {"Referer": base + "/student/jobs/index.html", "X-Requested-With": "XMLHttpRequest"}
    jobs: List[RawJob] = []
    seen = set()
    # 两路：通用(全部) + jobType=02(实习)。实习路把标题标注"（实习）"以进实习 Tab。
    for jtype, pages, is_intern in (("", PAGES, False), ("02", 4, True)):
        for page in range(1, pages + 1):
            params = (f"?jobType={jtype}&areaCode=&jobName=&monthPay=&industrySectors=&property="
                      f"&categoryCode=&memberLevel=&recruitType=&offset={page}&limit={PAGE_SIZE}"
                      f"&keyUnits=&degreeCode=&sourcesName=0&sourcesType=&_=1")
            try:
                data = get_json(ajax + params, headers=headers)
            except Exception:  # noqa: BLE001 — 单页失败不影响整体
                break
            lst = (data.get("data") or {}).get("list") or []
            if not lst:
                break
            for e in lst:
                jid = e.get("jobId") or ""
                if jid in seen:
                    continue
                seen.add(jid)
                name = e.get("jobName", "")
                if is_intern and "实习" not in name and "intern" not in name.lower():
                    name = f"{name}（实习）"   # jobType=02 即实习，标注以正确归入实习 Tab
                jd = " · ".join(filter(None, [
                    e.get("degreeName", ""), e.get("major", ""),
                    e.get("recProperty", ""), e.get("recScale", ""),
                    _salary(e), f"招{e.get('headCount','')}人" if e.get("headCount") else "",
                ]))
                jobs.append(RawJob(
                    company_name=e.get("recName") or e.get("companyName") or "",
                    title=name,
                    location=e.get("areaCodeName", ""),
                    publish_time=_date(e.get("publishDate") or e.get("updateDate")),
                    official_url=(detail + jid) if jid else "",
                    jd_text=jd,
                    raw={"platform": "ncss", "property": e.get("recProperty", ""),
                         "source": e.get("sourcesNameCh", ""), "salary": _salary(e),
                         "degree": e.get("degreeName", ""), "needs_ai": False},
                ))
    return jobs
