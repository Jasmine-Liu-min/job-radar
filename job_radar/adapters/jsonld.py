"""通用 schema.org JobPosting (JSON-LD) 解析器（跨站通用，对齐 Google for Jobs 标准）。

许多招聘/公司官网的职位详情页内嵌：
    <script type="application/ld+json">{"@type":"JobPosting", ...}</script>
这是 schema.org / Google for Jobs 的事实标准（字段：title/description/datePosted/
validThrough/hiringOrganization/jobLocation/baseSalary/employmentType/identifier）。

本 adapter **不针对单一站点**——对任何内嵌 JobPosting 的页面通用，endpoint = 页面 URL
（单职位详情，或含多个 JobPosting 的页面，均支持；自动处理 dict / list / @graph 三种形态）。

适用边界：国内大厂官网多为无 JSON-LD 的 SPA，本解析器主要对海外/SEO 优化站点有效；
作为"一次写好、跨站复用"的工具保留，新增此类源只需在 config/sources.csv 填 adapter=jsonld。

解析逻辑经离线单测覆盖（scripts/smoke_test.py 的 [D] JSON-LD 段）。
"""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Any, Dict, List

from ..models import RawJob
from . import register
from .http import get_text

_LD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S
)
_TAGS = re.compile(r"<[^>]+>")
_SP = re.compile(r"\s+")


def _text(v: Any) -> str:
    """从 str / {name|value} / list 里取一个可读字符串。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return _text(v.get("name") or v.get("value") or v.get("@value") or "")
    if isinstance(v, list):
        return ", ".join(filter(None, (_text(x) for x in v)))
    return str(v)


def _location(jp: Dict) -> str:
    if str(jp.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        req = jp.get("applicantLocationRequirements")
        return "远程" + (f"·{_text(req)}" if req else "")
    loc = jp.get("jobLocation")
    if isinstance(loc, list):
        loc = loc[0] if loc else None
    if isinstance(loc, dict):
        addr = loc.get("address") or {}
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"),
                     addr.get("addressCountry")]
            return _text([p for p in parts if p])
        return _text(addr)
    return _text(loc)


def _salary(jp: Dict) -> str:
    bs = jp.get("baseSalary")
    if not isinstance(bs, dict):
        return ""
    cur = bs.get("currency") or ""
    val = bs.get("value")
    if isinstance(val, dict):
        unit = val.get("unitText") or ""
        if val.get("minValue") or val.get("maxValue"):
            lo, hi = val.get("minValue", "?"), val.get("maxValue", "?")
            return f"{lo}-{hi} {cur}/{unit}".strip()
        if val.get("value"):
            return f"{val.get('value')} {cur}/{unit}".strip()
    elif val:
        return f"{val} {cur}".strip()
    return ""


def _collect(obj: Any, out: List[Dict]) -> None:
    """从任意 JSON-LD 结构里收集 @type==JobPosting 的对象（含 list / @graph）。"""
    if isinstance(obj, list):
        for x in obj:
            _collect(x, out)
    elif isinstance(obj, dict):
        if "@graph" in obj:
            _collect(obj["@graph"], out)
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if any(str(x).endswith("JobPosting") for x in types if x):
            out.append(obj)


def parse_jobs(html: str, page_url: str = "") -> List[RawJob]:
    """从页面 HTML 解析所有 JobPosting JSON-LD → RawJob 列表（纯函数，便于单测）。"""
    found: List[Dict] = []
    for block in _LD_RE.findall(html):
        raw = unescape(block.strip())
        try:
            found_obj = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            continue
        _collect(found_obj, found)

    jobs: List[RawJob] = []
    seen = set()
    for jp in found:
        title = _text(jp.get("title"))
        if not title:
            continue
        url = _text(jp.get("url")) or page_url
        key = (title, _text(jp.get("hiringOrganization")))
        if key in seen:
            continue
        seen.add(key)
        desc = _SP.sub(" ", _TAGS.sub(" ", unescape(_text(jp.get("description")))))[:4000]
        ident = jp.get("identifier")
        ident_str = _text(ident.get("value")) if isinstance(ident, dict) else _text(ident)
        jobs.append(RawJob(
            company_name=_text(jp.get("hiringOrganization")),
            title=title,
            location=_location(jp),
            publish_time=_text(jp.get("datePosted"))[:10],
            deadline=_text(jp.get("validThrough"))[:10],   # schema.org validThrough
            official_url=url,
            jd_text=desc,
            raw={"platform": "jsonld",
                 "employmentType": _text(jp.get("employmentType")),
                 "identifier": ident_str,
                 "salary": _salary(jp), "needs_ai": False},
        ))
    return jobs


@register("jsonld")
def fetch(endpoint: str) -> List[RawJob]:
    return parse_jobs(get_text(endpoint), endpoint)
