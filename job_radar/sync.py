"""主流程：读 config/sources.csv → 调 adapter → 归一化 → 去重 → 打分 → 写 data/。

对应规划 Phase 1。同时实现信源健康度闭环（规划第 9 章）：
- 逐信源 try/except，单源失败不影响整体；
- 记录 last_success_at / last_error / consecutive_failures；
- 连续失败达阈值自动把 status 降级 unstable → blocked；
- 产出 data/health_report.json，可随推送发送。

运行：python3 -m job_radar.sync
"""
from __future__ import annotations

import csv
import json
import os
import traceback
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .adapters import get_adapter
from .dedup import dedup
from .industry import classify as classify_industry
from .models import Job, RawJob, SOURCE_CONFIDENCE
from .normalize import make_dedup_key
from .quality_rules import quality_tags
from .score import score_job

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CONFIG_DIR = os.path.join(ROOT, "config")


def _path_with_legacy(primary: str, legacy: str) -> str:
    """Prefer the organized path while keeping old checkouts/scripts working."""
    return primary if os.path.exists(primary) else legacy


SOURCES_CSV = _path_with_legacy(os.path.join(CONFIG_DIR, "sources.csv"),
                                os.path.join(ROOT, "sources.csv"))
PROFILES_JSON = _path_with_legacy(os.path.join(CONFIG_DIR, "profiles.json"),
                                  os.path.join(ROOT, "profiles.json"))
STATE_JSON = os.path.join(DATA_DIR, "source_state.json")

# 连续失败降级阈值（规划第 9 章）
UNSTABLE_AT = 3
BLOCKED_AT = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sources(path: str = SOURCES_CSV) -> List[Dict[str, str]]:
    """读 config/sources.csv，跳过 # 开头的注释行与空行。"""
    rows: List[Dict[str, str]] = []
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    for r in reader:
        rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def _load_state(path: str = STATE_JSON) -> Dict[str, Dict]:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _to_jobs(src: Dict[str, str], raws: List[RawJob]) -> List[Job]:
    """RawJob → Job：补 source_id/org_type/可信度，生成 dedup_key。"""
    confidence = SOURCE_CONFIDENCE.get(src["source_type"], 50)
    out: List[Job] = []
    for r in raws:
        company = r.company_name or src["company_name"]
        key = make_dedup_key(company, r.title, r.location)
        out.append(Job(
            job_id=f"{src['source_id']}:{key}",
            dedup_key=key,
            source_id=src["source_id"],
            company_name=company,
            title=r.title,
            location=r.location,
            org_type=src["org_type"],
            industry=classify_industry(company, r.title, r.jd_text, src["org_type"]),
            publish_time=r.publish_time,
            deadline=r.deadline,
            official_url=r.official_url,
            salary=str(r.raw.get("salary", "")),   # adapter 若抽到薪资则带上（规划 5.2）
            employment_type=str(r.raw.get("employmentType", "")),
            identifier=str(r.raw.get("identifier", "")),
            jd_text=r.jd_text,
            source_confidence=confidence,
            extra=r.raw,                            # 保留 adapter 全部附加字段，避免落盘丢失
        ))
    return out


def _merge_incremental(current: List[Dict], store_path: str, now: str,
                       scoped_source_ids: Optional[set] = None) -> Dict:
    """把本次快照增量合并进已有 jobs.json（只保留当前在架岗位）。

    - 新岗位：追加，first_seen=now。
    - 已有岗位：刷新 last_seen，保留用户 status 与原 first_seen，gone=False。
    - 本次未出现的旧岗位：视为已下线，直接从主库移除。
    - scoped_source_ids 有值时，仅替换这些 source_id 的旧岗位；其它来源原样保留。
    返回 {"jobs": [...], "new": n, "gone": n, "active": n}。
    """
    old: Dict[str, Dict] = {}
    if os.path.exists(store_path):
        try:
            with open(store_path, encoding="utf-8") as f:
                for r in json.load(f):
                    if r.get("dedup_key"):
                        old[r["dedup_key"]] = r
        except (ValueError, OSError):
            old = {}

    out: Dict[str, Dict] = {}
    if scoped_source_ids is not None:
        for k, r in old.items():
            if r.get("source_id") not in scoped_source_ids:
                out[k] = r

    seen = set()
    new_cnt = 0
    for d in current:
        k = d.get("dedup_key")
        if not k:
            continue
        seen.add(k)
        o = old.get(k)
        if o:
            d["first_seen"] = o.get("first_seen") or now
            d["status"] = o.get("status") or "new"   # 保留用户状态（收藏/忽略/已投递）
            # 累计历史出现次数
            d["seen_count"] = max(int(d.get("seen_count", 1)), int(o.get("seen_count", 1)))
        else:
            d["first_seen"] = now
            new_cnt += 1
        d["last_seen"] = now
        d["gone"] = False
        out[k] = d

    if scoped_source_ids is not None:
        gone_rows = [r for k, r in old.items()
                     if r.get("source_id") in scoped_source_ids and k not in seen]
    else:
        gone_rows = [r for k, r in old.items() if k not in seen]
    gone_cnt = len(gone_rows)

    jobs = sorted(out.values(), key=lambda d: d.get("match_score", 0), reverse=True)
    return {"jobs": jobs, "new": new_cnt, "gone": gone_cnt,
            "active": len(jobs), "gone_jobs": gone_rows}


def _archive_gone(path: str, rows: List[Dict], now: str, limit: int = 10000) -> int:
    """把下线/消失岗位写入轻量归档，不污染当前在架库。"""
    if not rows:
        return 0
    archive: Dict[str, Dict] = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                for r in json.load(f):
                    key = r.get("dedup_key")
                    if key:
                        archive[key] = r
        except (ValueError, OSError):
            archive = {}
    for r in rows:
        key = r.get("dedup_key")
        if not key:
            continue
        archive[key] = {
            "dedup_key": key,
            "source_id": r.get("source_id", ""),
            "company_name": r.get("company_name", ""),
            "title": r.get("title", ""),
            "location": r.get("location", ""),
            "official_url": r.get("official_url", ""),
            "first_seen": r.get("first_seen", ""),
            "last_seen": r.get("last_seen", ""),
            "archived_at": now,
            "match_score": r.get("match_score", 0),
        }
    vals = sorted(archive.values(), key=lambda r: r.get("archived_at", ""), reverse=True)[:limit]
    _save_json(path, vals)
    return len(vals)


def _degrade(status: str, fails: int) -> str:
    if fails >= BLOCKED_AT:
        return "blocked"
    if fails >= UNSTABLE_AT:
        return "unstable"
    return "active" if status in ("active", "unstable") else status


def run(only_adapters: Optional[set] = None, only_source_ids: Optional[set] = None,
        verbose: bool = True, out_dir: Optional[str] = None,
        preserve_unselected: bool = False) -> Dict:
    """执行一次同步。

    only_adapters: 仅跑指定 adapter（smoke test 用，只跑稳定信源）。
    only_source_ids: 仅跑指定 source_id（日常核心源快刷用）。
    out_dir: 输出目录；默认写正式的 data/。smoke test 传临时目录，避免覆盖正式数据。
    preserve_unselected: 只刷新部分源时，保留其它来源旧数据。
    """
    data_dir = out_dir or DATA_DIR
    state_path = os.path.join(data_dir, "source_state.json")
    jobs_path = os.path.join(data_dir, "jobs.json")
    archive_path = os.path.join(data_dir, "jobs_archive.json")
    run_ts = _now()
    sources = read_sources()
    state = _load_state(state_path)
    with open(PROFILES_JSON, encoding="utf-8") as pf:
        profiles = json.load(pf)
    selected_source_ids = {s["source_id"] for s in sources
                           if (not only_adapters or s["adapter"] in only_adapters)
                           and (not only_source_ids or s["source_id"] in only_source_ids)}

    all_jobs: List[Job] = []
    health: List[Dict] = []
    success_source_ids = set()

    for src in sources:
        sid, adapter_name = src["source_id"], src["adapter"]
        if only_adapters and adapter_name not in only_adapters:
            continue
        if only_source_ids and sid not in only_source_ids:
            continue
        # deprecated=已弃用；blocked=已知反爬/登录墙，需 Playwright 等手段，暂不尝试。
        # 两者都跳过抓取，但仍登记进健康报告，作为待处理 backlog 可见。
        if src.get("status") in ("deprecated", "blocked"):
            health.append({"source_id": sid, "adapter": adapter_name,
                           "status": src["status"], "skipped": True,
                           "note": src.get("notes", "")})
            continue

        st = state.setdefault(sid, {"consecutive_failures": 0, "status": src.get("status", "active")})
        try:
            raws = get_adapter(adapter_name)(src["endpoint"])
            jobs = _to_jobs(src, raws)
            all_jobs.extend(jobs)
            n = len(jobs)
            # 静默失效检测（规划第 9 章）：源不报错但抓取量异常时告警。
            # peak = 历史最高抓取量，作为基线；跌为 0 或骤降 >80% 视为疑似改版/失效。
            peak = max(int(st.get("peak_count", 0)), n)
            alert = ""
            if peak >= 5 and n == 0:
                alert = f"抓取量跌为 0（历史峰值 {peak}，疑似改版/失效）"
            elif peak >= 10 and n < peak * 0.2:
                alert = f"抓取量骤降 {peak}→{n}（疑似部分失效）"
            # 0 条且触发异常告警时，不把该源视为可替换快照，避免临时接口异常误下线旧岗位。
            if not (n == 0 and alert):
                success_source_ids.add(sid)
            st.update(consecutive_failures=0, status="active", last_success_at=_now(),
                      last_error="", last_count=n, peak_count=peak, alert=alert)
            if verbose:
                mark = "⚠" if alert else "✓"
                print(f"  {mark} {sid:<16} {n:>4} jobs" + (f"  ⚠ {alert}" if alert else ""))
        except Exception as e:  # noqa: BLE001 — 健康度闭环要捕获所有失败
            st["consecutive_failures"] = st.get("consecutive_failures", 0) + 1
            st["status"] = _degrade(st.get("status", "active"), st["consecutive_failures"])
            st["last_error"] = f"{type(e).__name__}: {e}"
            if verbose:
                print(f"  ✗ {sid:<16} FAIL ({st['consecutive_failures']}x → {st['status']}): {type(e).__name__}: {e}")
                if os.environ.get("JOB_RADAR_DEBUG"):
                    traceback.print_exc()
        health.append({"source_id": sid, "adapter": adapter_name, **st})

    ran_source_ids = {h["source_id"] for h in health}
    for src in sources:
        sid = src["source_id"]
        if sid in ran_source_ids:
            continue
        st = dict(state.get(sid, {}))
        status = st.get("status") or src.get("status", "active")
        health.append({"source_id": sid, "adapter": src["adapter"], **st,
                       "status": status, "not_run": True})

    # 释放可能由 SPA adapter 启动的共享浏览器（无则无操作）
    from .adapters import _pw
    _pw.shutdown()

    # 去重（规划 5.4）
    before = len(all_jobs)
    jobs = dedup(all_jobs)
    removed = before - len(jobs)

    # 规则粗分（规划 4.1）：对所有画像取得分最高者，应用其分数/标签；
    # 风险标记与去重阶段已有的（如 repeat_posting）合并，不覆盖。
    for job in jobs:
        best = None
        for prof in profiles.values():
            r = score_job(job, prof)
            if best is None or r.score > best.score:
                best = r
        if best is not None:
            job.match_score = best.score
            # 行业作为首位标签，技术关键词随后（推送同时带行业 + 技术标签）
            tags = ([f"行业:{job.industry}"] if job.industry else []) + best.tags
            qtags, qrisks = quality_tags(job)
            job.tags = list(dict.fromkeys(tags + qtags))
            job.risk_flags = list(dict.fromkeys(job.risk_flags + best.risk_flags + qrisks))

    # 增量合并入库（新增追加、下线移除、保留用户状态）
    scoped_ids = success_source_ids if preserve_unselected else None

    if not jobs and scoped_ids is None and os.path.exists(jobs_path):
        try:
            with open(jobs_path, encoding="utf-8") as f:
                old_count = len(json.load(f))
        except (ValueError, OSError):
            old_count = 0
        if old_count:
            raise RuntimeError(
                f"本次抓取快照为 0，但已有库有 {old_count} 条；拒绝全量标下线。"
                " 请检查网络/权限或改用单源加性导入。"
            )
    merged = _merge_incremental([j.to_dict() for j in jobs], jobs_path, run_ts, scoped_ids)
    archived_total = _archive_gone(archive_path, merged.get("gone_jobs", []), run_ts)

    # 落盘
    _save_json(jobs_path, merged["jobs"])
    _save_json(state_path, state)
    report = {
        "generated_at": run_ts,
        "sources_total": len(selected_source_ids),
        "sources_catalog_total": len(sources),
        "preserve_unselected": preserve_unselected,
        "jobs_raw": before,
        "snapshot_after_dedup": len(jobs),
        "duplicates_removed": removed,
        "store_total": len(merged["jobs"]),
        "new_this_run": merged["new"],
        "gone_total": merged["gone"],
        "archived_total": archived_total,
        "active_total": merged["active"],
        "unhealthy": [h for h in health if h.get("status") in ("unstable", "blocked")],
        "alerts": [{"source_id": h["source_id"], "alert": h["alert"]}
                   for h in health if h.get("alert")],
        "sources": health,
    }
    _save_json(os.path.join(data_dir, "health_report.json"), report)

    if verbose:
        print(f"\n本次快照 {len(jobs)} 条（去重掉 {removed}）"
              f" → 入库累积 {len(merged['jobs'])} 条"
              f"（新增 {merged['new']}，在架 {merged['active']}，已下线 {merged['gone']}）")
        print(f"数据: {jobs_path}   健康报告: {os.path.join(data_dir, 'health_report.json')}")
    return report


if __name__ == "__main__":
    run()
