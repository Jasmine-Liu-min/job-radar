"""牛客网 校招/实习（Playwright 渲染，绕过反爬 + 字体加密）。

牛客是学生最全的校招/实习聚合，但纯 HTTP 取不到（SPA + 反爬）。用无头浏览器渲染后，
卡片文本（职位/薪资/城市/届别）就能直接读——浏览器会执行反爬 JS 并正确渲染字体。

endpoint = 列表页 URL：
    https://www.nowcoder.com/jobs/intern/center    实习
    https://www.nowcoder.com/jobs/fulltime/center   校招/全职
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
_SAL = re.compile(r"(\d[\d.]*\s*[-~]\s*\d[\d.]*\s*(?:元/天|元/月|K|k)[^ \n，]*|\d+-\d+K·\d+薪)")
_CO = re.compile(r"[一-龥A-Za-z0-9（）()·]{2,24}?(公司|科技|集团|股份|有限|银行|"
                 r"研究院|研究所|网络|信息|技术|数据|智能|半导体|医药|生物|汽车|电子)")
PAGES = 8   # 翻页深度（每页 ~20，列表用 ?page= 翻页）


@register("nowcoder")
def fetch(endpoint: str) -> List[RawJob]:
    from . import _pw
    rows = []
    seen_h = set()
    # 牛客是重型 SPA：复用同一标签页改 ?page= 不会重载，须**每页开新标签**全量导航
    for n in range(1, PAGES + 1):
        page = _pw.new_page()
        try:
            page.set_default_timeout(30000)
            try:
                page.goto(_with_page(endpoint, n), wait_until="networkidle", timeout=30000)
            except Exception:  # noqa: BLE001 — SPA 长轮询，等不到 networkidle 也继续
                pass
            page.wait_for_timeout(3000)
            batch = page.eval_on_selector_all(
                "a[href*='/job']",
                "els=>els.map(e=>({t:(e.innerText||'').trim(), h:e.href})).filter(x=>x.t.length>8)")
        finally:
            page.close()
        fresh = [b for b in batch if b["h"] not in seen_h]
        for b in fresh:
            seen_h.add(b["h"])
        rows += fresh
        if not fresh:                  # 本页无新链接 = 已到末页
            break

    jobs: List[RawJob] = []
    seen = set()
    _NOISE = ("求职首页", "发布职位", "全部职位", "求职", "首页", "登录", "注册")
    for r in rows:
        t, h = r.get("t", ""), r.get("h", "")
        lines = [l.strip() for l in t.split("\n") if l.strip()]
        if not lines:
            continue
        title = lines[0]
        key = (title, lines[1] if len(lines) > 1 else "")
        if key in seen or len(title) < 3 or title in _NOISE:
            continue
        seen.add(key)
        m = _SAL.search(t)
        sal = re.sub(r"\s+", "", m.group(0)) if m else ""
        mc = _CITY.search(t)
        loc = mc.group(0) if mc else ""
        comp = ""
        for l in lines[1:]:
            mm = _CO.search(l)
            if mm and len(l) <= 24:
                comp = mm.group(0)
                break
        jobs.append(RawJob(
            company_name=comp, title=title, location=loc,
            official_url=h, jd_text=t[:500],
            raw={"platform": "nowcoder", "salary": sal, "needs_ai": False}))
    return jobs
