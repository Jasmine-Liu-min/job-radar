"""Lever 公开 postings API（P1 海外 ATS）。

endpoint = company slug，例如 "netflix"。
API: https://api.lever.co/v0/postings/{slug}?mode=json
"""
from __future__ import annotations

from typing import List

from ..models import RawJob
from . import register
from .http import get_json


@register("lever")
def fetch(endpoint: str) -> List[RawJob]:
    url = f"https://api.lever.co/v0/postings/{endpoint}?mode=json"
    data = get_json(url)
    jobs: List[RawJob] = []
    for j in data:
        cats = j.get("categories") or {}
        # Lever createdAt 是毫秒时间戳；不做时区换算，转 ISO 留待归一化
        ts = j.get("createdAt")
        publish = ""
        if isinstance(ts, (int, float)):
            # 仅保留可复现的 UTC 日期字符串
            import datetime
            publish = datetime.datetime.utcfromtimestamp(ts / 1000).isoformat() + "Z"
        jobs.append(RawJob(
            company_name=endpoint,
            title=j.get("text", ""),
            location=cats.get("location", ""),
            publish_time=publish,
            official_url=j.get("hostedUrl", ""),
            jd_text=(j.get("descriptionPlain") or "")[:4000],
            raw={"id": j.get("id")},
        ))
    return jobs
