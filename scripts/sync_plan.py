#!/usr/bin/env python3
"""统一刷新入口。

用法：
  python3 scripts/sync_plan.py fast     # 日常快扫：稳定 API/HTML 源，不碰 Playwright 慢源
  python3 scripts/sync_plan.py slow     # 慢源补扫：牛客/实习僧/SPA 高校等
  python3 scripts/sync_plan.py full     # 深扫：全部 active 源
  python3 scripts/sync_plan.py smart    # 周一到周六 fast，周日 full
  python3 scripts/sync_plan.py rescore  # 只重新打分并导出
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from job_radar import sync  # noqa: E402
from job_radar.models import Job  # noqa: E402
from job_radar.quality_rules import quality_tags  # noqa: E402
from job_radar.score import score_job  # noqa: E402
from scripts import export_html  # noqa: E402

CORE_SOURCE_IDS = {"cn-iguopin", "gov-sasac", "gov-qyzp"}
ROLE_SOURCE_IDS = {
    "cn-bytedance",
    "cn-tencent",
    "cn-tencent-campus",
    "cn-jd",
    "cn-netease",
    "cn-sensetime",
    "cn-horizon",
    "cn-iguopin",
}


def _active_sources() -> list[dict[str, str]]:
    return [s for s in sync.read_sources() if s.get("status") in ("active", "unstable")]


def _priority(src: dict[str, str]) -> int:
    try:
        return int(src.get("priority") or 9)
    except ValueError:
        return 9


def _fast_source_ids() -> set[str]:
    """日常快扫：优先稳定、低成本、高收益信源。

    原则：
    - 不跑 Playwright/community 慢源，避免每天卡很久。
    - 保留优先级 1/2 的 API/HTML 源，覆盖国聘、国家平台、央企公告、大厂/外企官网。
    - 旧数据通过 preserve_unselected 留在库里，慢源等周日或手动补扫。
    """
    ids: set[str] = set()
    for src in _active_sources():
        sid = src["source_id"]
        method = src.get("fetch_method", "")
        source_type = src.get("source_type", "")
        if method == "playwright" or source_type == "community":
            continue
        if _priority(src) <= 2 or sid.startswith("gov-") or sid == "cn-iguopin":
            ids.add(sid)
    return ids | CORE_SOURCE_IDS | ROLE_SOURCE_IDS


def _slow_source_ids() -> set[str]:
    """慢源补扫：浏览器渲染、社区聚合、低优先级补充源。"""
    ids: set[str] = set()
    for src in _active_sources():
        if src.get("fetch_method") == "playwright" or src.get("source_type") == "community" or _priority(src) >= 3:
            ids.add(src["source_id"])
    return ids


def _run_sources(label: str, ids: set[str]) -> None:
    if not ids:
        raise SystemExit(f"{label} 没有可运行信源")
    print(f"🚦 {label}: {len(ids)} 个信源")
    sync.run(only_source_ids=ids, preserve_unselected=True)
    export_html.main()


def _is_deep_day() -> bool:
    now = dt.datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.weekday() == 6  # Sunday


def rescore() -> None:
    path = os.path.join(sync.DATA_DIR, "jobs.json")
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    with open(sync.PROFILES_JSON, encoding="utf-8") as f:
        profiles = json.load(f)

    changed = 0
    for d in rows:
        job = Job(**{k: v for k, v in d.items() if k in Job.__dataclass_fields__})
        best = max((score_job(job, p) for p in profiles.values()), key=lambda r: r.score)
        tags = ([f"行业:{job.industry}"] if job.industry else []) + best.tags
        qtags, qrisks = quality_tags(job)
        new_tags = list(dict.fromkeys(tags + qtags))
        new_risks = list(dict.fromkeys((job.risk_flags or []) + best.risk_flags + qrisks))
        if d.get("match_score") != best.score or d.get("tags") != new_tags:
            changed += 1
        d["match_score"] = best.score
        d["tags"] = new_tags
        d["risk_flags"] = new_risks

    rows.sort(key=lambda r: r.get("match_score", 0), reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"✅ 重新打分 {len(rows)} 条，变化 {changed} 条")
    export_html.main()


def run_plan(plan: str) -> None:
    if plan == "smart":
        plan = "full" if _is_deep_day() else "fast"
        print(f"🧭 smart -> {plan}")
    if plan == "fast":
        _run_sources("日常快扫", _fast_source_ids())
        return
    if plan == "slow":
        _run_sources("慢源补扫", _slow_source_ids())
        return
    if plan == "core":
        sync.run(only_source_ids=CORE_SOURCE_IDS, preserve_unselected=True)
        export_html.main()
        return
    if plan == "role":
        sync.run(only_source_ids=ROLE_SOURCE_IDS, preserve_unselected=True)
        export_html.main()
        return
    if plan == "full":
        sync.run(preserve_unselected=True)
        export_html.main()
        return
    if plan == "rescore":
        rescore()
        return
    raise SystemExit(f"未知 plan: {plan}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="统一刷新招聘雷达数据。")
    p.add_argument("plan", choices=["smart", "fast", "slow", "core", "role", "full", "rescore"])
    args = p.parse_args(argv)
    run_plan(args.plan)


if __name__ == "__main__":
    main()
