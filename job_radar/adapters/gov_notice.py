"""通用政府/央国企招聘公告列表解析器（P3 权威官方源）。

很多权威官方源是"服务端渲染的公告列表"，结构一致：一串 <a> 链接，文字或 title
属性是公告标题（公司名常嵌在标题里），点进去是公告原文。本 adapter 通用解析这类页面：
endpoint = 列表页 URL，按招聘信号词过滤、相对链接转绝对、从标题轻量抽公司名。

已接入：
    国资委 人事招聘（央企公告最权威源）http://www.sasac.gov.cn/.../index.html
    中国公共招聘网·中央企业招聘应届高校毕业生信息公开 /qyzp/index.jhtml

详情页会轻量抽取发布时间、报名/投递截止时间和正文摘要；岗位明细/资格条件/
编制类型等高维结构化仍留给后续 AI 抽取（规划 7 章）。
比旧的 public_notice 占位更通用——后者按链接文本弱过滤，抓不到 title 属性式条目。
"""
from __future__ import annotations

import re
import ssl
from datetime import datetime
from html import unescape
from typing import Iterable, List
from urllib.parse import urljoin

from ..models import RawJob
from . import register
from .http import get_text

MAX_ITEMS = 50
MAX_DETAIL_ITEMS = 18
_SIGNAL = re.compile(r"(招聘|公告|启事|校园|校招|社招|引才|引进|遴选|选聘|公开招|补招)")
# 具体性判据：真公告通常含年份/届次/单位实体；据此滤掉"事业单位公开招聘"这类导航泛栏目
_SPECIFIC = re.compile(r"(20\d{2}|\d{4}年|届|公司|集团|银行|股份|有限|研究院|研究所|总院|总部|中心|学院|大学)")
_COMPANY_CUT = re.compile(
    r"(20\d{2}|\d{4}年|年度|届|校园招聘|校招|社会招聘|社招|招聘|公告|启事|公开|信息公开|专场|补招)"
)
# 明显的导航/非公告条目
_NAV = re.compile(r"^(首页|更多|下一页|上一页|返回|中国公共招聘网|登录|注册|>|·)")

_LAX_SSL = ssl.create_default_context()
_LAX_SSL.check_hostname = False
_LAX_SSL.verify_mode = ssl.CERT_NONE

# <a ...>：抓 href + 标题（title 属性优先，否则取链接文本）
_A_TAG = re.compile(r'<a\b([^>]*?)href="([^"]+)"([^>]*?)>(.*?)</a>', re.S)
_TITLE_ATTR = re.compile(r'title="([^"]{4,80})"')
_TAGS = re.compile(r"<[^>]+>")
_SP = re.compile(r"\s+")
_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_DATE = re.compile(r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?")
_PUBLISH_CTX = re.compile(r"(发布时间|发布日期|发布于|时间|日期)\D{0,16}" + _DATE.pattern)
_DEADLINE_CTX = re.compile(
    r"(报名截止|投递截止|简历投递截止|申请截止|网申截止|截止时间|截至|截止日期|"
    r"报名时间|投递时间|简历接收时间)\D{0,120}" + _DATE.pattern,
    re.S,
)


def _company(title: str) -> str:
    m = _COMPANY_CUT.search(title)
    name = (title[: m.start()] if m else title).strip(" -—·:：【】《》")
    return name or title


def _get(url: str) -> str:
    try:
        return get_text(url, timeout=8)
    except Exception:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8, context=_LAX_SSL) as r:
            return r.read().decode("utf-8", "replace")


def _get_detail(url: str) -> str:
    """详情页只做短平快补充：不重试、限字节，避免慢页面卡住全量同步。"""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=4, context=_LAX_SSL) as r:
        return r.read(220000).decode("utf-8", "replace")


def _norm_date(parts: Iterable[str]) -> str:
    y, m, d = [int(x) for x in parts]
    return f"{y:04d}-{m:02d}-{d:02d}"


def _text(html: str) -> str:
    html = _SCRIPT_STYLE.sub(" ", html)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|li|tr|h\d)>", "\n", html, flags=re.I)
    return _SP.sub(" ", unescape(_TAGS.sub(" ", html))).strip()


def _detail(url: str) -> tuple[str, str, str]:
    """返回 (publish_time, deadline, jd_text)。详情失败时给空值，避免拖垮整源。"""
    try:
        text = _text(_get_detail(url))
    except Exception:  # noqa: BLE001
        return "", "", ""
    publish = ""
    mp = _PUBLISH_CTX.search(text[:1800])
    if mp:
        publish = _norm_date(mp.groups()[-3:])
    deadline = ""
    dates = []
    for md in _DEADLINE_CTX.finditer(text):
        # 截止/报名时间窗口常写成 "2026年6月20日至2026年7月5日"，取窗口最后一天。
        dates.extend(_norm_date(m.groups()) for m in _DATE.finditer(md.group(0)))
    if dates:
        # "报名时间：2026-06-20 至 2026-07-05" 这类窗口取最后一天。
        deadline = sorted(dates)[-1]
    elif "截止" in text or "截至" in text:
        # 少数写法是"请于 2026-07-05 前..."，仅在含截止语义时保守兜底。
        all_dates = [_norm_date(m.groups()) for m in _DATE.finditer(text[:6000])]
        futureish = [d for d in all_dates if d >= f"{datetime.now().year}-01-01"]
        if futureish:
            deadline = sorted(futureish)[-1]
    return publish, deadline, text[:900]


@register("gov_notice")
def fetch(endpoint: str) -> List[RawJob]:
    html = _get(endpoint)
    seen = set()
    jobs: List[RawJob] = []
    for pre, href, post, inner in _A_TAG.findall(html):
        mt = _TITLE_ATTR.search(pre) or _TITLE_ATTR.search(post)
        title = unescape(mt.group(1)).strip() if mt else \
            unescape(_SP.sub(" ", _TAGS.sub("", inner)).strip())
        if not title or len(title) < 6 or _NAV.match(title):
            continue
        if not _SIGNAL.search(title) or not _SPECIFIC.search(title):
            continue
        url = urljoin(endpoint, href)
        if url in seen or url.rstrip("/") == endpoint.rstrip("/"):
            continue
        seen.add(url)
        if len(jobs) < MAX_DETAIL_ITEMS:
            publish, deadline, jd_text = _detail(url)
        else:
            publish, deadline, jd_text = "", "", ""
        jobs.append(RawJob(
            company_name=_company(title),
            title=title,
            publish_time=publish,
            deadline=deadline,
            official_url=url,
            jd_text=jd_text or title,
            raw={"platform": "gov_notice", "needs_ai": not bool(deadline)},
        ))
        if len(jobs) >= MAX_ITEMS:
            break
    return jobs
