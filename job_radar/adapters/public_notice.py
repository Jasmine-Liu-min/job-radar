"""央国企/事业单位公告 adapter（P3，本项目差异化核心）。

公告类页面没有统一结构，本 adapter 是一个**占位骨架**：
- 现状：抓回页面纯文本，按很弱的启发式切分出疑似公告条目，可信度低。
- 目标（Phase 3）：在这里接 AI 抽取，把公告原文结构化为带"报名截止/资格条件/
  编制类型（编制/合同制/劳务派遣/外包）"的标准岗位（规划 3.4 / 7 章）。

之所以先留骨架而不强行解析：每个站点 DOM 不同，硬写正则维护成本极高，
正确做法是 per-site 规则或 AI 抽取。这里先保证链路能跑通、能登记健康度。
"""
from __future__ import annotations

import re
from html import unescape
from typing import List

from ..models import RawJob
from . import register
from .http import get_text

_TAG_RE = re.compile(r"<[^>]+>")
# 公告标题里常见的招聘信号词，用于弱过滤
_SIGNAL = re.compile(r"(招聘|公告|招录|引进|选聘|公开招|拟聘)")


@register("public_notice")
def fetch(endpoint: str) -> List[RawJob]:
    html = get_text(endpoint)
    # 取所有链接文本作为候选公告标题（极弱启发式，仅占位）
    candidates = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
    jobs: List[RawJob] = []
    seen = set()
    for href, text in candidates:
        title = _TAG_RE.sub("", unescape(text)).strip()
        if not title or len(title) < 6 or not _SIGNAL.search(title):
            continue
        if title in seen:
            continue
        seen.add(title)
        url = href if href.startswith("http") else endpoint.rstrip("/") + "/" + href.lstrip("/")
        jobs.append(RawJob(
            company_name="",          # 公告主体待 AI 抽取
            title=title,
            location="",
            official_url=url,
            jd_text=title,            # 详情待进入详情页或 AI 抽取
            raw={"extraction": "stub", "needs_ai": True},
        ))
        if len(jobs) >= 30:
            break
    return jobs
