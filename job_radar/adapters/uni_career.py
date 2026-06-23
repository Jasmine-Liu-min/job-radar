"""高校就业网通用 adapter（"新锦成"系就业平台，P3 高校渠道）。

不少 985/211 高校就业网用同一套服务端渲染平台，URL 指纹一致：
    /campus/view/id/N   校园招聘公告
    /teachin/view/id/N  宣讲会
    /jobfair/view/id/N  招聘会
    /vip/user/login     单位/学生登录入口

已验证同平台的学校（endpoint 即各校就业网根域名）：
    中山大学 career.sysu.edu.cn、中南大学 career.csu.edu.cn

两种条目写法都支持：
    a) <a title="标题" href="/teachin/view/id/N">      （中大）
    b) <a href="/teachin/view/id/N">单位名/标题</a>     （中南，链接文本即内容）

抓取分两步（轻量增强）：先解析首页列表拿标题+链接；再逐条进详情页用正则抽
最稳字段——完整单位名（<title>）、日期、校区。单条详情失败自动降级。
完整正文结构化（岗位明细/报名方式/截止/编制类型）留待 Phase 3 接 AI（规划 3.4/7）。

新增一所同平台学校：只需在 config/sources.csv 加一行，adapter=uni_career，endpoint 填根域名。
"""
from __future__ import annotations

import re
import ssl
from html import unescape
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from ..models import RawJob
from . import register
from .http import get_text

# 单校单次最多进多少详情页（礼貌 + 控时延）
MAX_DETAIL = 25

# host 关键字 → 学校名，用于给 location 加学校前缀；未知则用 host
_SCHOOL_BY_HOST = {
    "sysu": "中山大学", "csu": "中南大学", "scu": "四川大学", "whu": "武汉大学",
    "nankai": "南开大学", "ruc": "中国人民大学", "seu": "东南大学",
}

_VIEW_RE = re.compile(
    r'<a\b([^>]*?)href="(/(?:campus|teachin|jobfair)/view/(?:id/)?\d+)"([^>]*)>(.*?)</a>',
    re.S,
)
_ATTR_TITLE_RE = re.compile(r'title="([^"]{4,80})"')
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

_TITLE_RE = re.compile(r"<title>([^<]+)</title>")
_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")
_CAMPUS_RE = re.compile(r"(东校园|西校园|南校园|北校园|本部|.{0,4}校区)")
_DEADLINE_RE = re.compile(
    r"(?:截止|报名截止|投递截止)\D{0,6}(20\d{2}-\d{2}-\d{2}|\d{1,2}月\d{1,2}日)"
)
_ORG_HINT = re.compile(r"(公司|集团|银行|股份|有限|科技|研究院|大学|学院|医院|事业|中心|局|厂|所|部队|实验室)")
# 详情页 <title> 有时是站点名（如"中南大学就业信息网"），不能当雇主名
_SITE_NAME = re.compile(r"(就业(信息)?网|招聘网|就业指导|服务中心|就业创业|career)")
_COMPANY_CUT = re.compile(r"(20\d{2}|\d{4}年|届|校园招聘|校招|招聘|宣讲会|实习|双选|提前批)")

# 高校就业网偶有过期证书，放宽校验（仅本类信源）
_LAX_SSL = ssl.create_default_context()
_LAX_SSL.check_hostname = False
_LAX_SSL.verify_mode = ssl.CERT_NONE


def _school_of(base: str) -> str:
    host = urlparse(base).hostname or ""
    for key, name in _SCHOOL_BY_HOST.items():
        if key in host:
            return name
    return host


def _list_title(attrs: str, tail: str, inner: str) -> str:
    """条目标题：优先 title 属性（中大），否则取链接文本（中南）。"""
    m = _ATTR_TITLE_RE.search(attrs) or _ATTR_TITLE_RE.search(tail)
    if m:
        return unescape(m.group(1)).strip()
    txt = _SPACE_RE.sub(" ", _TAG_RE.sub("", inner)).strip()
    return unescape(txt)


def _company_from_title(title: str) -> str:
    m = _COMPANY_CUT.search(title)
    name = (title[: m.start()] if m else title).strip(" -—·:：")
    return name or title


def _enrich(url: str, list_title: str, school: str) -> RawJob:
    company = _company_from_title(list_title)
    location = school
    publish, deadline = "", ""
    try:
        html = get_text(url)  # http 层已带重试；证书问题见下方 fallback
    except Exception:
        html = ""
    if not html:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=12, context=_LAX_SSL) as r:
                html = r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            html = ""
    if html:
        mt = _TITLE_RE.search(html)
        if mt:
            t = unescape(mt.group(1)).strip()
            # 仅当 <title> 像真实单位名、且不是站点名时，才用它覆盖列表标题推断的公司
            if _ORG_HINT.search(t) and not _SITE_NAME.search(t) and len(t) <= 40:
                company = t
        dates = _DATE_RE.findall(html)
        if dates:
            publish = dates[0]
        camps = list(dict.fromkeys(c.strip() for c in _CAMPUS_RE.findall(html) if c.strip()))
        if camps:
            location = f"{school}·" + "·".join(camps[:3])
        md = _DEADLINE_RE.search(html)
        if md:
            deadline = md.group(1)
    return RawJob(
        company_name=company,
        title=list_title,
        location=location,
        publish_time=publish,
        deadline=deadline,
        official_url=url,
        jd_text=list_title,
        raw={"platform": "xjc", "school": school,
             "kind": url.split("/view/")[0].rsplit("/", 1)[-1], "needs_ai": True},
    )


@register("uni_career")
def fetch(endpoint: str) -> List[RawJob]:
    base = endpoint.rstrip("/")
    school = _school_of(base)
    html = get_text(base + "/")

    seen = set()
    entries: List[Tuple[str, str]] = []
    for attrs, path, tail, inner in _VIEW_RE.findall(html):
        if path in seen:
            continue
        title = _list_title(attrs, tail, inner)
        if not title or len(title) < 4:
            continue
        seen.add(path)
        url = path if path.startswith("http") else base + path
        entries.append((url, title))

    jobs: List[RawJob] = []
    for url, title in entries[:MAX_DETAIL]:
        jobs.append(_enrich(url, title, school))
    return jobs
