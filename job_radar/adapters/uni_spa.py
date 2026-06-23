"""SPA 高校就业网通用 adapter（Playwright 渲染，P3 高校渠道）。

江浙沪等高校（复旦/上交/浙大/南大）就业网是纯前端 SPA：HTML 是空壳，岗位数据
由 JS 异步渲染。纯标准库抓不到，故用 Playwright 启无头浏览器跑完 JS 再抽 DOM。

设计：
- **可选依赖**：playwright 未安装时抛清晰错误，由健康度闭环记账降级，不影响其它信源。
  安装：pip install playwright && python -m playwright install chromium
- **通用提取**：渲染后取所有 <a>，保留 href 像岗位/公告详情、且文本含公司线索的，
  从文本块里拆出 职位名 / 公司名 / 日期（多数 SPA 卡片是"标题\\n公司\\n日期"结构）。
- 每个 endpoint 独立启浏览器（隔离、简单）；单次有超时上限。

新增同类 SPA 学校：config/sources.csv 加一行，adapter=uni_spa，endpoint 填首页 URL。
DOM 差异大时，可在 _SCHOOL_HINT 里按 host 加专属过滤，或后续接 AI 从渲染文本抽取。
"""
from __future__ import annotations

import re
from typing import List
from urllib.parse import urlparse

from ..models import RawJob
from . import register

NAV_TIMEOUT_MS = 30000
SETTLE_MS = 2500
MAX_ITEMS = 40

_SCHOOL_BY_HOST = {
    "fudan": "复旦大学", "sjtu": "上海交通大学", "zju": "浙江大学",
    "nju": "南京大学", "tongji": "同济大学", "ecnu": "华东师范大学",
}
# 岗位/宣讲会详情链接特征（收紧：只认真正的岗位/宣讲路由，排除 news/通知等导航）
# 覆盖：复旦 zhiwei/zhaopin、南大 fulltime_info_detail/special_recruit_detail 等 hash 路由
_JOB_HREF = re.compile(
    r"(zhiwei|zhaopin|jobdetail|positiondetail|position/|preach|xuanjiang|jobfair"
    r"|recruit_detail|info_detail|fulltime|special_recruit)", re.I)
_DATE = re.compile(r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|20\d{2}[-/.]\d{1,2})")
_ORG_HINT = re.compile(r"(公司|集团|银行|股份|有限|科技|研究院|研究所|大学|学院|医院|事业|中心|实验室|部队|局)")
_NOISE = re.compile(r"^(更多|查看更多|详情|报名|投递|首页|登录|注册)")
# 单行卡片里从标题截公司名（如"深圳市韶音科技有限公司专场招聘会"→ 公司部分）
_COMPANY_CUT = re.compile(r"(专场|校园招聘|校招|招聘会|招聘|宣讲会|双选|空中|提前批|实习)")


def _school_of(url: str) -> str:
    host = urlparse(url).hostname or ""
    for key, name in _SCHOOL_BY_HOST.items():
        if key in host:
            return name
    return host


def _parse_block(text: str, school: str):
    """从卡片文本块拆 (title, company, date)。"""
    lines = [l.strip() for l in re.split(r"[\r\n]+", text) if l.strip()]
    if not lines:
        return None
    title = lines[0]
    company = ""
    # 1) 优先：独立的公司行（多行卡片，如复旦"职位\n公司\n日期"）
    for l in lines[1:]:
        if _ORG_HINT.search(l) and len(l) <= 40:
            company = l
            break
    # 2) 兜底：公司名嵌在标题里（单行卡片，如南大"韶音科技...专场招聘会"）
    if not company and _ORG_HINT.search(title):
        m = _COMPANY_CUT.search(title)
        company = (title[: m.start()] if m else title).strip(" -—·:：")
    md = _DATE.search(text)
    date = md.group(1).replace("/", "-").replace(".", "-") if md else ""
    return title, company, date


@register("uni_spa")
def fetch(endpoint: str) -> List[RawJob]:
    from . import _pw  # 共享浏览器（可选依赖；未装 playwright 时抛 RuntimeError）

    school = _school_of(endpoint)
    rows = []
    page = _pw.new_page()
    try:
        page.set_default_timeout(NAV_TIMEOUT_MS)
        try:
            page.goto(endpoint, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
        except Exception:
            # networkidle 等不到也继续——很多 SPA 有长轮询
            pass
        page.wait_for_timeout(SETTLE_MS)
        rows = page.eval_on_selector_all(
            "a",
            "els => els.map(e => ({t: (e.innerText||'').trim(), h: e.href}))"
            ".filter(x => x.t.length > 5)",
        )
    finally:
        page.close()

    seen = set()
    jobs: List[RawJob] = []
    for r in rows:
        text, href = r.get("t", ""), r.get("h", "")
        if not href or not _JOB_HREF.search(href) or _NOISE.match(text):
            continue
        parsed = _parse_block(text, school)
        if not parsed:
            continue
        title, company, date = parsed
        # 真岗位卡片都带公司名；据此过滤掉导航/通知/新闻等噪声
        if len(title) < 5 or not company:
            continue
        key = (company, title)
        if key in seen:
            continue
        seen.add(key)
        jobs.append(RawJob(
            company_name=company or school,
            title=title,
            location=school,
            publish_time=date,
            official_url=href,
            jd_text=text[:1000],
            raw={"platform": "spa", "school": school, "needs_ai": True},
        ))
        if len(jobs) >= MAX_ITEMS:
            break
    return jobs
