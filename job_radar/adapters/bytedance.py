"""字节跳动招聘官网接口（P0 国内官网，差异化重点之一）。

endpoint = 官网根 URL（仅用于记录，实际打固定 API）。
接口: POST https://jobs.bytedance.com/api/v1/search/job/posts

注意：国内官网常有反爬/风控，可能返回非 200 或验证页。失败不需在 adapter 里
吞掉——直接抛出，由 sync.py 的健康度闭环（规划第 9 章）统一记账并降级。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from ..models import RawJob
from ..keyword_config import role_focus_keywords
from . import register
from .http import post_json

_API = "https://jobs.bytedance.com/api/v1/search/job/posts"
PAGES = 10        # 通用 feed 深翻页数（每页 20）
INTERN_PAGES = 6  # "实习"关键词补全页数
FOCUS_PAGES = 2


def _ts_to_date(ts) -> str:
    """字节的 publish_time 是 epoch 秒/毫秒 → YYYY-MM-DD。"""
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return ""
    if ts > 1e12:        # 毫秒
        ts //= 1000
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def _query(keyword: str, offset: int, headers: dict) -> list:
    body = {"keyword": keyword, "limit": 20, "offset": offset,
            "job_category_id_list": [], "location_code_list": [],
            "subject_id_list": [], "recruitment_id_list": []}
    data = post_json(_API, body, headers=headers)
    return (data.get("data") or {}).get("job_post_list", []) or []


@register("bytedance")
def fetch(endpoint: str) -> List[RawJob]:
    headers = {"Referer": "https://jobs.bytedance.com/",
               "portal-channel": "office", "portal-platform": "pc"}
    jobs: List[RawJob] = []
    seen = set()
    # 通用 feed 深翻 + 目标方向关键词补全，避免算法/数据科学岗位被默认排序漏掉。
    plans = [("", PAGES)] + [(kw, INTERN_PAGES if kw == "实习" else FOCUS_PAGES)
                             for kw in role_focus_keywords()]
    for kw, pages in plans:
        for page in range(pages):
            try:
                posts = _query(kw, page * 20, headers)
            except Exception:  # noqa: BLE001 — 翻页中途失败即停，已抓到的保留
                break
            if not posts:
                break
            for p in posts:
                pid = p.get("id")
                if pid in seen:
                    continue
                seen.add(pid)
                city = ", ".join(c.get("name", "") for c in (p.get("city_list") or []))
                jobs.append(RawJob(
                    company_name="字节跳动",
                    title=p.get("title", ""),
                    location=city or p.get("city_info", {}).get("name", ""),
                    publish_time=_ts_to_date(p.get("publish_time")),
                    official_url=f"https://jobs.bytedance.com/experienced/position/{p.get('id','')}/detail",
                    jd_text=(p.get("description") or "")[:4000],
                    raw={"id": pid},
                ))
            if len(posts) < 20:
                break
    return jobs
