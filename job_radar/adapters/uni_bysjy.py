"""高校就业网通用 adapter（"bysjy"系毕业生就业平台，P3 高校渠道）。

第二套常见高校就业平台，URL 指纹：
    /detail/career?id=N   宣讲会/招聘会
    /detail/news?id=N     招聘公告/选调/公示
    外链 hr.bysjy.com.cn   单位端入口

已验证同平台学校（endpoint 填各校就业网根域名）：
    湖南大学 scc.hnu.edu.cn、暨南大学 career.jnu.edu.cn、华南师范大学 career.scnu.edu.cn

与 uni_career（新锦成系）的区别：列表条目文本自带日期/时间前缀，形如
    "10 2026-06 江苏省...公示"            （news：日 + 年-月 + 标题）
    "06/11 14:00 过 ...专题宣讲会"         （career：月/日 时:分 + 状态 + 标题）
本 adapter 在列表页就能拿到标题与日期，故**不逐条进详情页**（更快、更省请求）。
公司/单位名从标题做轻量启发式；完整结构化留待 Phase 3 接 AI（规划 3.4/7）。

新增同平台学校：config/sources.csv 加一行，adapter=uni_bysjy，endpoint 填根域名。
"""
from __future__ import annotations

import re
import ssl
from html import unescape
from typing import List
from urllib.parse import urlparse

from ..models import RawJob
from . import register
from .http import get_text

_SCHOOL_BY_HOST = {
    "hnu": "湖南大学", "jnu": "暨南大学", "scnu": "华南师范大学",
    "gzhu": "广州大学", "szu": "深圳大学",
}

_ITEM_RE = re.compile(
    r'<a\b[^>]*href="(/detail/(?:career|news)\?id=\d+[^"]*)"[^>]*>(.*?)</a>', re.S
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
# 列表文本里的日期：news 形如 "10 2026-06 标题" → 拼成 2026-06-10
_NEWS_DATE = re.compile(r"^(\d{1,2})\s+(20\d{2})-(\d{2})\b")
# career 形如 "06/11 14:00 过 标题"
_CAREER_PREFIX = re.compile(r"^\d{1,2}\s*/\s*\d{1,2}\s+\d{1,2}:\d{2}\s*")
_STATUS = re.compile(r"^(过|即将开始|预告|报名中|进行中|已结束)\s*")
_LEAD_NUM = re.compile(r"^[\d\s/:\-年月日]+")
_COMPANY_CUT = re.compile(r"(20\d{2}|\d{4}年|届|校园招聘|校招|招聘会|招聘|宣讲会|双选|专场|公示|公告|选调)")
# 明显的导航/非岗位条目，跳过
_NAV = {"联系我们", "更多", "查看更多", "更多>>", "首页"}
# news 频道混有行政通知（档案转递/去向登记等），只保留招聘相关；career（宣讲会）全留
_JOB_SIGNAL = re.compile(r"(招聘|宣讲|校招|双选|引才|选调|招录|专场|岗位|入职|人才|实习|招考)")

_LAX_SSL = ssl.create_default_context()
_LAX_SSL.check_hostname = False
_LAX_SSL.verify_mode = ssl.CERT_NONE


def _school_of(base: str) -> str:
    host = urlparse(base).hostname or ""
    for key, name in _SCHOOL_BY_HOST.items():
        if key in host.split("."):
            return name
    for key, name in _SCHOOL_BY_HOST.items():
        if key in host:
            return name
    return host


def _parse(inner: str, is_career: bool):
    """返回 (clean_title, publish_iso)。"""
    text = unescape(_SPACE_RE.sub(" ", _TAG_RE.sub(" ", inner)).strip())
    publish = ""
    if is_career:
        text = _CAREER_PREFIX.sub("", text)
        text = _STATUS.sub("", text)
    else:
        m = _NEWS_DATE.match(text)
        if m:
            day, year, mon = m.group(1), m.group(2), m.group(3)
            publish = f"{year}-{mon}-{int(day):02d}"
        text = _LEAD_NUM.sub("", text)
    return text.strip(" -—·:："), publish


def _company_from_title(title: str) -> str:
    m = _COMPANY_CUT.search(title)
    name = (title[: m.start()] if m else title).strip(" -—·:：")
    return name or title


def _get(url: str) -> str:
    try:
        return get_text(url)
    except Exception:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12, context=_LAX_SSL) as r:
            return r.read().decode("utf-8", "replace")


@register("uni_bysjy")
def fetch(endpoint: str) -> List[RawJob]:
    base = endpoint.rstrip("/")
    school = _school_of(base)
    html = _get(base + "/")

    seen = set()
    jobs: List[RawJob] = []
    for path, inner in _ITEM_RE.findall(html):
        if path in seen:
            continue
        is_career = "/detail/career" in path
        title, publish = _parse(inner, is_career)
        if not title or len(title) < 5 or title in _NAV:
            continue
        # news 频道过滤掉非招聘的行政通知；宣讲会(career)一律保留
        if not is_career and not _JOB_SIGNAL.search(title):
            continue
        seen.add(path)
        url = path if path.startswith("http") else base + path
        jobs.append(RawJob(
            company_name=_company_from_title(title),
            title=title,
            location=school,
            publish_time=publish,
            official_url=url,
            jd_text=title,
            raw={"platform": "bysjy", "school": school,
                 "kind": "career" if is_career else "news", "needs_ai": True},
        ))
    return jobs
