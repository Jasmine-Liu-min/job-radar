"""腾讯招聘官网接口（P0 国内官网，差异化重点之一）。

endpoint = 官网根 URL（仅记录）。
接口: GET https://careers.tencent.com/tencentcareer/api/post/Query

同样可能受风控影响，失败由 sync.py 健康度闭环兜底（规划第 9 章）。
"""
from __future__ import annotations

import urllib.parse
from typing import List

from ..models import RawJob
from ..keyword_config import role_focus_keywords
from . import register
from .http import get_json

_API = "https://careers.tencent.com/tencentcareer/api/post/Query"
PAGES = 10        # 通用 feed 深翻页数（每页 20）
INTERN_PAGES = 6  # "实习"关键词补全页数
FOCUS_PAGES = 2


def _query(keyword: str, page: int) -> list:
    params = {"timestamp": "0", "keyword": keyword, "pageIndex": str(page),
              "pageSize": "20", "language": "zh-cn", "area": "cn"}
    url = _API + "?" + urllib.parse.urlencode(params)
    data = get_json(url, headers={"Referer": "https://careers.tencent.com/"})
    return (data.get("Data") or {}).get("Posts", []) or []


@register("tencent")
def fetch(endpoint: str) -> List[RawJob]:
    jobs: List[RawJob] = []
    seen = set()
    # 通用 feed 深翻 + 目标方向关键词补全，避免算法/数据科学岗位被默认排序漏掉。
    plans = [("", PAGES)] + [(kw, INTERN_PAGES if kw == "实习" else FOCUS_PAGES)
                             for kw in role_focus_keywords()]
    for kw, pages in plans:
        for page in range(1, pages + 1):
            try:
                posts = _query(kw, page)
            except Exception:  # noqa: BLE001 — 翻页中途失败即停
                break
            if not posts:
                break
            for p in posts:
                pid = p.get("PostId")
                if pid in seen:
                    continue
                seen.add(pid)
                jobs.append(RawJob(
                    company_name="腾讯",
                    title=p.get("RecruitPostName", ""),
                    location=p.get("LocationName", ""),
                    publish_time=p.get("LastUpdateTime", ""),
                    official_url=p.get("PostURL", ""),
                    jd_text=(p.get("Responsibility") or "")[:4000],
                    raw={"id": pid},
                ))
            if len(posts) < 20:
                break
    return jobs
