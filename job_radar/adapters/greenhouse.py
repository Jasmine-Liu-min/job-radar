"""Greenhouse 公开 Job Board API（P1 海外 ATS，最稳定）。

endpoint = board token，例如 "stripe"。
API: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true
"""
from __future__ import annotations

import re
from html import unescape
from typing import List

from ..models import RawJob
from . import register
from .http import get_json

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    return _TAG_RE.sub(" ", unescape(s or "")).strip()


@register("greenhouse")
def fetch(endpoint: str) -> List[RawJob]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{endpoint}/jobs?content=true"
    data = get_json(url)
    jobs: List[RawJob] = []
    for j in data.get("jobs", []):
        jobs.append(RawJob(
            company_name=endpoint,
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            publish_time=j.get("updated_at", "") or j.get("first_published", ""),
            official_url=j.get("absolute_url", ""),
            jd_text=_strip_html(j.get("content", ""))[:4000],
            raw={"id": j.get("id")},
        ))
    return jobs
