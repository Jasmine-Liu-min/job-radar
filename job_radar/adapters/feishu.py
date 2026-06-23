"""飞书招聘 ATS 通用 adapter（Playwright 捕获，P0/P1 国内官网）。

大量国内公司(尤其新能源/硬科技：蔚来/理想/小鹏/商汤/地平线/货拉拉等)用"飞书招聘"
托管官网，域名形如 <sub>.jobs.feishu.cn。其职位接口 /api/v1/search/job/posts 需要
JS 生成的 _signature 反爬签名，直连会 405；用 Playwright 加载页面（浏览器生成签名）
并**捕获该接口响应**即可拿到真实岗位。与字节(jobs.bytedance.com)同后端。

endpoint = 公司招聘站根 URL（如 https://nio.jobs.feishu.cn/）。公司中文名由
config/sources.csv 的 company_name 列提供（adapter 输出 company 留空，sync 兜底填充）。

可选依赖：未装 playwright 时抛 RuntimeError，由健康度闭环降级。
新增飞书公司：config/sources.csv 加一行 adapter=feishu，endpoint 填其 *.jobs.feishu.cn 根域名。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import List
from urllib.parse import urlparse

from ..models import RawJob
from . import register

NAV_TIMEOUT_MS = 30000
SETTLE_MS = 3000
_API_MARK = "/api/v1/search/job/posts"


def _ts_to_date(ts) -> str:
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return ""
    if ts > 1e12:
        ts //= 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d") if ts > 0 else ""


@register("feishu")
def fetch(endpoint: str) -> List[RawJob]:
    from . import _pw  # 共享浏览器（可选依赖）

    base = endpoint.rstrip("/")
    sub = (urlparse(base).hostname or "").split(".")[0]
    captured: List[str] = []

    def on_resp(resp):
        if _API_MARK in resp.url:
            try:
                captured.append(resp.text())
            except Exception:  # noqa: BLE001
                pass

    page = _pw.new_page()
    try:
        page.on("response", on_resp)
        page.set_default_timeout(NAV_TIMEOUT_MS)
        try:
            page.goto(base + "/index", wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(SETTLE_MS)
            if not captured:
                page.goto(base + "/index/position/", wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(SETTLE_MS)
        except Exception:
            pass
    finally:
        page.close()

    if not captured:
        raise RuntimeError("未捕获到飞书职位接口响应（可能非飞书站或反爬变更）")

    posts = []
    for body in captured:
        try:
            d = json.loads(body)
            posts = (d.get("data") or {}).get("job_post_list") or posts
        except (ValueError, json.JSONDecodeError):
            continue

    jobs: List[RawJob] = []
    seen = set()
    for p in posts:
        pid = str(p.get("id") or "")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        city = ", ".join(c.get("name", "") for c in (p.get("city_list") or []) if c.get("name")) \
            or (p.get("city_info") or {}).get("name", "")
        jobs.append(RawJob(
            company_name="",   # 由 config/sources.csv 的 company_name 兜底（中文公司名）
            title=p.get("title", ""),
            location=city,
            publish_time=_ts_to_date(p.get("publish_time")),
            official_url=f"{base}/position/{pid}/detail",
            jd_text=(p.get("description") or "")[:4000],
            raw={"platform": "feishu", "id": pid},
        ))
    return jobs
