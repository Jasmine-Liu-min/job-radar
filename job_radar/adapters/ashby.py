"""Ashby 公开 posting API（P1 海外 ATS）。

endpoint = job board name，例如 "ramp"。
API: https://api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true
"""
from __future__ import annotations

from typing import List

from ..models import RawJob
from . import register
from .http import get_json


@register("ashby")
def fetch(endpoint: str) -> List[RawJob]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{endpoint}?includeCompensation=true"
    data = get_json(url)
    jobs: List[RawJob] = []
    for j in data.get("jobs", []):
        jobs.append(RawJob(
            company_name=endpoint,
            title=j.get("title", ""),
            location=j.get("location", ""),
            publish_time=j.get("publishedAt", "") or j.get("updatedAt", ""),
            official_url=j.get("jobUrl", ""),
            jd_text=(j.get("descriptionPlain") or "")[:4000],
            raw={"id": j.get("id"), "employmentType": j.get("employmentType")},
        ))
    return jobs
