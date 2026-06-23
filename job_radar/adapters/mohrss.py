"""中国公共招聘网 / 人社部公共就业服务（P3 国家级官方，分省）。

人社部主办的全国公共招聘平台（job.mohrss.gov.cn），聚合各省市公共就业服务岗位。
职位列表服务端渲染：整页岗位以 JSON 数组塞在隐藏 input `findjoblist` 的 value 里，
**无反爬**，直接 urllib 取页面再解析即可。

按用户关注，仅抓 广东/湖南/浙江/江苏/上海 五省市——用 AREA=<省码>0000 服务端过滤
（如 AREA=440000&AREA_name=广东省）。客户端按地区码过滤命中率极低（实测百里挑四），
故必须走服务端 AREA 参数。

字段映射（人社系统字段是代码）：
    aca112 职位名 / aab004 单位 / area_ 市 / aab302 区县
    acb241-acb242 薪资(元/月) / acb22a 经验 / acb228 招聘人数
    s_aae395 发布 / s_aae398 截止 / ace760 详情外链 / aab001 职位id / aab301 地区码
"""
from __future__ import annotations

import json
import re
import urllib.parse
from html import unescape
from typing import List

from ..models import RawJob
from . import register
from .http import get_text

_BASE = "http://job.mohrss.gov.cn/cjobs/jobinfolist/listJobinfolist"
_HEADERS = {"Referer": "http://job.mohrss.gov.cn/"}

# 用户关注的 5 省市（省级国标码 + 名称）
PROVINCES = [
    ("440000", "广东省"), ("430000", "湖南省"), ("330000", "浙江省"),
    ("320000", "江苏省"), ("310000", "上海市"),
]
PAGES_PER_PROVINCE = 2

_FINDLIST_RE = re.compile(r'name="findjoblist"\s+value="')


def _salary(e: dict) -> str:
    lo, hi = e.get("acb241"), e.get("acb242")
    if lo or hi:
        return f"{lo or '?'}-{hi or '?'}元/月"
    return ""


def _parse_page(html: str) -> List[dict]:
    m = _FINDLIST_RE.search(html)
    if not m:
        return []
    try:
        arr, _ = json.JSONDecoder().raw_decode(unescape(html[m.end():m.end() + 400000]))
        return arr if isinstance(arr, list) else []
    except (ValueError, json.JSONDecodeError):
        return []


@register("mohrss")
def fetch(endpoint: str) -> List[RawJob]:
    jobs: List[RawJob] = []
    seen = set()
    for code, name in PROVINCES:
        for page in range(1, PAGES_PER_PROVINCE + 1):
            url = (f"{_BASE}?pageNo={page}&orderType=score"
                   f"&AREA={code}&AREA_name={urllib.parse.quote(name)}")
            try:
                html = get_text(url, headers=_HEADERS, timeout=8)
            except Exception:  # noqa: BLE001 — 单页失败不影响其它省/页
                break
            recs = _parse_page(html)
            if not recs:
                break
            for e in recs:
                jid = str(e.get("aab001") or "")
                if jid in seen:
                    continue
                seen.add(jid)
                title = e.get("aca112") or e.get("aca111_") or ""
                if not title:
                    continue
                city = e.get("area_") or ""
                district = e.get("aab302") or ""
                loc = (city + (district if district and district != city else "")).strip() or name
                jd = " · ".join(filter(None, [
                    e.get("aca111_", ""), e.get("acb22a", ""), _salary(e),
                    f"招{e.get('acb228')}人" if e.get("acb228") else "",
                ]))
                url_detail = e.get("ace760") or ""
                if not url_detail.startswith("http"):
                    url_detail = f"http://job.mohrss.gov.cn/cjobs/jobinfo/showDetail?aab001={jid}"
                jobs.append(RawJob(
                    company_name=e.get("aab004") or "",
                    title=title,
                    location=loc,
                    publish_time=(e.get("s_aae395") or "")[:10],
                    deadline=(e.get("s_aae398") or "")[:10],
                    official_url=url_detail,
                    jd_text=jd,
                    raw={"platform": "mohrss", "province": name,
                         "area_code": e.get("aab301", ""), "salary": _salary(e),
                         "needs_ai": False},
                ))
    return jobs
