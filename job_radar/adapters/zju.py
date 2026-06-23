"""浙江大学就业网（P3 高校渠道，纯 JSON 接口）。

浙大就业网 career.zju.edu.cn 是 Vue SPA，首页 DOM 无 <a>，但其数据接口是开放 JSON、
且**无反爬**，直接 urllib 即可（无需 Playwright）：
    /v5-api/jyxt/wzsy/getZhXjhList.zf?xxdm=10335   宣讲会(含空中宣讲会)
    /v5-api/jyxt/wzsy/getZhZphList.zf?xxdm=10335   招聘会/双选会
xxdm=10335 是浙大的学校代码。

字段：
    宣讲会 xjhmc 名称 / xjhrq 日期 / xjhcdmc 场地 / tzljdz 通知链接
    招聘会 zphmc 名称 / zphrq 日期 / cdmc  场地 / tzljdz 通知链接
endpoint 仅作记录，实际打固定 v5-api。换学校代码即可复用到同平台其它学校。
"""
from __future__ import annotations

import re
from typing import List

from ..models import RawJob
from . import register
from .http import get_json

_XXDM = "10335"
_BASE = "https://www.career.zju.edu.cn/v5-api/jyxt/wzsy"
_SITE = "https://www.career.zju.edu.cn"
_HEADERS = {"Referer": "https://www.career.zju.edu.cn/"}
_COMPANY_CUT = re.compile(r"(宣讲会|招聘会|双选会|空中|专场|校园招聘|校招|启动|暨|实践|招才|引智|引才|活动|2027|2026)")


def _company(title: str) -> str:
    m = _COMPANY_CUT.search(title)
    name = (title[: m.start()] if m else title).strip(" -—·:：【】！")
    return name or title


def _url(e: dict, kind: str) -> str:
    """Build the same detail URL as the ZJU SPA.

    `tzljdz` is often empty, but the list payload carries stable ids. Use those
    ids instead of leaving cards unclickable.
    """
    u = (e.get("tzljdz") or "").strip()
    if u.startswith("http"):
        return u
    if e.get("sjlx") == "2":
        xid = e.get("xjhbh") or e.get("zphbh")
        return f"{_SITE}/notification/detail?xwid={xid}" if xid else ""
    if kind == "xjh":
        xjhbh = e.get("xjhbh") or ""
        dwxxid = e.get("dwxxid") or ""
        if xjhbh:
            return f"{_SITE}/jyxt/sczp/xjhgl/ckXjhgwXq.zf?xjhbh={xjhbh}&dwxxid={dwxxid}"
    if kind == "zph":
        zphbh = e.get("zphbh") or ""
        if zphbh:
            return f"{_SITE}/jyxt/sczp/zphgl/ckZphsqdw.zf?zphbh={zphbh}"
    return ""


@register("zju")
def fetch(endpoint: str) -> List[RawJob]:
    jobs: List[RawJob] = []
    seen = set()

    def add(title, date, place, e, kind):
        title = (title or "").strip()
        if not title or title in seen:
            return
        seen.add(title)
        jobs.append(RawJob(
            company_name=_company(title),
            title=title,
            location="浙江大学" + (f"·{place}" if place else ""),
            publish_time=(date or "")[:10],
            official_url=_url(e, kind),
            jd_text=title,
            raw={"platform": "zju-api", "school": "浙江大学", "needs_ai": True},
        ))

    # 宣讲会
    try:
        d = get_json(f"{_BASE}/getZhXjhList.zf?xxdm={_XXDM}&limit=30", headers=_HEADERS)
        for e in d.get("result", []):
            add(e.get("xjhmc"), e.get("xjhrq"), e.get("xjhcdmc"), e, "xjh")
    except Exception:  # noqa: BLE001 — 单接口失败不影响另一个
        pass
    # 招聘会/双选会
    try:
        d = get_json(f"{_BASE}/getZhZphList.zf?xxdm={_XXDM}&limit=30", headers=_HEADERS)
        for e in d.get("result", []):
            add(e.get("zphmc"), e.get("zphrq"), e.get("cdmc"), e, "zph")
    except Exception:  # noqa: BLE001
        pass

    return jobs
