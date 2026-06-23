"""上海交通大学就业网（P3 高校渠道，Playwright + 接口捕获）。

上交就业网 www.job.sjtu.edu.cn 有 JS 反爬挑战，且岗位/宣讲会数据不在 DOM 的 <a> 里，
而是异步请求 `/career/index/common/jyrl`（就业日历）返回 JSON。纯 urllib 会被反爬挡下
（返回 JS 挑战页），故用 Playwright：浏览器执行完挑战 JS 后，**监听并捕获**该接口响应。

可选依赖：未装 playwright 时抛清晰错误，由健康度闭环降级（同 uni_spa）。

日历 JSON 结构：data[].con[] 每个事件含
    con  宣讲会/活动名称   jbrq 举办日期   cdmc 场地   a 详情相对链接(xjhxx/view/<id>)
"""
from __future__ import annotations

import json
import re
from typing import List

from ..models import RawJob
from . import register

NAV_TIMEOUT_MS = 30000
SETTLE_MS = 3000
_CAL_API = "/career/index/common/jyrl"
_INDEX = "https://www.job.sjtu.edu.cn/career/index"
_BASE = "https://www.job.sjtu.edu.cn/career/"
_COMPANY_CUT = re.compile(r"(宣讲会|招聘会|专场|校园招聘|校招|双选|空中|开放日|快闪|招募|2027|2026)")


def _company(title: str) -> str:
    m = _COMPANY_CUT.search(title)
    name = (title[: m.start()] if m else title).strip(" -—·:：【】")
    return name or title


@register("sjtu")
def fetch(endpoint: str) -> List[RawJob]:
    from . import _pw  # 共享浏览器（可选依赖；未装 playwright 时抛 RuntimeError）

    captured: List[str] = []

    def on_resp(resp):
        if _CAL_API in resp.url:
            try:
                captured.append(resp.text())
            except Exception:  # noqa: BLE001
                pass

    page = _pw.new_page()
    try:
        page.on("response", on_resp)
        page.set_default_timeout(NAV_TIMEOUT_MS)
        try:
            page.goto(_INDEX, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(SETTLE_MS)
            if not captured:  # 首次可能仅过挑战，未触发接口；再导航一次
                page.goto(_INDEX, wait_until="networkidle", timeout=NAV_TIMEOUT_MS)
                page.wait_for_timeout(SETTLE_MS)
        except Exception:
            pass
    finally:
        page.close()

    if not captured:
        raise RuntimeError("未捕获到上交就业日历接口响应（反爬挑战或接口变更）")

    data = json.loads(captured[-1])
    events = [e for grp in data.get("data", []) for e in grp.get("con", [])]
    jobs: List[RawJob] = []
    seen = set()
    for e in events:
        title = (e.get("con") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        rel = (e.get("a") or "").lstrip("/")
        url = (_BASE + rel) if rel else _INDEX
        jobs.append(RawJob(
            company_name=_company(title),
            title=title,
            location="上海交通大学" + (f"·{e.get('cdmc','')}" if e.get("cdmc") else ""),
            publish_time=(e.get("jbrq") or "")[:10],
            official_url=url,
            jd_text=title,
            raw={"platform": "sjtu-cal", "school": "上海交通大学", "needs_ai": True},
        ))
    return jobs
