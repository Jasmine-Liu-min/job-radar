#!/usr/bin/env python3
"""统一刷新入口。

用法：
  python3 scripts/sync_plan.py core     # 国聘 + 央企公告
  python3 scripts/sync_plan.py role     # 数据/算法/产品/决策核心官网源
  python3 scripts/sync_plan.py full     # 全量同步
  python3 scripts/sync_plan.py rescore  # 只重新打分并导出
"""
from __future__ import annotations

import argparse
import json
import os
import sys

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
    if plan == "core":
        sync.run(only_source_ids=CORE_SOURCE_IDS, preserve_unselected=True)
        export_html.main()
        return
    if plan == "role":
        sync.run(only_source_ids=ROLE_SOURCE_IDS, preserve_unselected=True)
        export_html.main()
        return
    if plan == "full":
        sync.run()
        export_html.main()
        return
    if plan == "rescore":
        rescore()
        return
    raise SystemExit(f"未知 plan: {plan}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="统一刷新招聘雷达数据。")
    p.add_argument("plan", choices=["core", "role", "full", "rescore"])
    args = p.parse_args(argv)
    run_plan(args.plan)


if __name__ == "__main__":
    main()
