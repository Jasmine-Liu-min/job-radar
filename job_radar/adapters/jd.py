"""京东招聘官网接口（P0 国内官网，差异化重点之一）。

endpoint = 官网根 URL（仅记录）。
接口: POST https://zhaopin.jd.com/web/job/job_list  返回岗位 JSON 数组。
"""
from __future__ import annotations

from typing import List

from ..models import RawJob
from ..keyword_config import role_focus_keywords
from . import register
from .http import post_json

_API = "https://zhaopin.jd.com/web/job/job_list"
PAGES = 10        # 通用 feed 深翻页数（每页 30）
INTERN_PAGES = 5  # "实习"关键词补全页数
FOCUS_PAGES = 2


def _query(keyword: str, page: int) -> list:
    body = {"pageNum": page, "pageSize": 30, "keyword": keyword}
    data = post_json(_API, body, headers={"Referer": "https://zhaopin.jd.com/"})
    return data if isinstance(data, list) else (data.get("data") or [])


@register("jd")
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
                pid = p.get("id") or p.get("positionId") or ""
                if pid in seen:
                    continue
                seen.add(pid)
                jd = " ".join(filter(None, [p.get("workContent", ""), p.get("qualification", "")]))
                jobs.append(RawJob(
                    company_name="京东",
                    title=p.get("positionName", ""),
                    location=p.get("workCity", ""),
                    publish_time=p.get("formatPublishTime", "") or p.get("publishTime", ""),
                    official_url=f"https://zhaopin.jd.com/web/job/job_detail/{pid}",
                    jd_text=jd[:4000],
                    raw={"id": pid, "jobType": p.get("jobType", "")},
                ))
            if len(posts) < 30:
                break
    return jobs
