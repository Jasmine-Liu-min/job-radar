"""实习僧（Playwright 渲染，绕过反爬）。

实习僧是专门的实习平台。纯 HTTP 取不到（反爬 + 数字字体加密），但浏览器渲染后
职位/公司/城市可读（仅薪资是 PUA 字体加密、渲染态也是乱码，故略过薪资）。

endpoint = 列表页 URL：https://www.shixiseng.com/interns（可带 ?keyword= 等）
"""
from __future__ import annotations

import re
import urllib.parse
from typing import List

from ..models import RawJob
from . import register


def _with_page(url: str, n: int) -> str:
    parts = urllib.parse.urlparse(url)
    q = dict(urllib.parse.parse_qsl(parts.query))
    q["page"] = str(n)
    return parts._replace(query=urllib.parse.urlencode(q)).geturl()

_CITY = re.compile(r"(北京|上海|深圳|广州|杭州|成都|武汉|南京|苏州|西安|天津|重庆|长沙|"
                   r"合肥|厦门|珠海|东莞|无锡|宁波|济南|青岛|郑州|福州|大连|远程)")
_PUA = re.compile("[-]")   # 私有区字形(字体加密薪资),剔除
PAGES = 8   # 翻页深度（每页 ~20，列表用 ?page= 翻页）


@register("shixiseng")
def fetch(endpoint: str) -> List[RawJob]:
    from . import _pw
    page = _pw.new_page()
    rows = []
    seen_h = set()
    try:
        page.set_default_timeout(15000)
        for n in range(1, PAGES + 1):
            try:
                page.goto(_with_page(endpoint, n), wait_until="domcontentloaded", timeout=15000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(1600)
            batch = page.eval_on_selector_all(
                "a[href*='/intern/inn_']",
                "els=>els.map(e=>{let c=e.closest('li')||e.closest('div[class]')||e;"
                "return {ti:(e.innerText||'').trim(), t:(c.innerText||'').trim(), h:e.href}})")
            fresh = [b for b in batch if b["h"].split("?")[0] not in seen_h]
            for b in fresh:
                seen_h.add(b["h"].split("?")[0])
            rows += fresh
            if not fresh:
                break
    finally:
        try:
            page.close()
        except Exception:  # noqa: BLE001
            pass

    jobs: List[RawJob] = []
    seen = set()
    for r in rows:
        h = (r.get("h") or "").split("?")[0]
        title = _PUA.sub("", r.get("ti", "")).strip(" /|-")
        t = _PUA.sub("", r.get("t", "")).strip()   # 卡片全文（去加密字形）
        if not h or h in seen:
            continue
        lines = [l.strip(" /|") for l in t.split("\n") if l.strip(" /|")]
        if not title and lines:
            title = lines[0]
        if len(title) < 3 or title in ("实习", "校招", "公司"):
            continue
        seen.add(h)
        mc = _CITY.search(t)
        loc = mc.group(0) if mc else ""
        # 公司：含 公司/科技/集团 等的行（实习僧卡片有独立公司行，如"萌想科技（实习僧）"）
        comp = ""
        for l in lines[1:]:
            if re.search(r"(公司|科技|集团|股份|有限|网络|信息|技术|数据|智能|教育|医药|生物)", l) and len(l) <= 26:
                comp = re.sub(r"（实习僧）|\(实习僧\)", "", l).strip()
                break
        jobs.append(RawJob(
            company_name=comp, title=title, location=loc,
            official_url=h, jd_text=t[:400],
            raw={"platform": "shixiseng", "needs_ai": False}))
    return jobs
