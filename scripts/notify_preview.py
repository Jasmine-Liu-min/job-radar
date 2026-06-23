#!/usr/bin/env python3
"""生成自动化推送预览。

先把"该推什么"稳定下来，再接飞书/企业微信/邮件 webhook。
默认输出 data/notify_preview.md，供人工检查或 GitHub Actions commit。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
JOBS = os.path.join(DATA_DIR, "jobs.json")
HEALTH = os.path.join(DATA_DIR, "health_report.json")
INBOX = os.path.join(DATA_DIR, "inbox", "nowcoder_discovered.txt")
OUT = os.path.join(DATA_DIR, "notify_preview.md")
STATE = os.path.join(DATA_DIR, "notify_state.json")
DEFAULT_WORKBENCH_URL = os.getenv("WORKBENCH_URL", "").strip()

LOW = {"代招/委托", "猎头", "劳务派遣", "泛销售", "低相关管培", "地点风险", "缺官网链接"}
BIG = {"腾讯", "字节跳动", "网易", "京东", "百度", "快手", "阿里", "美团", "拼多多"}
WEAK = re.compile(r"机械|电气|材料|外贸|英语|市场营销|生产|设备|工艺|质检|采购|销售|兼职|校园大使|大专|技术员|理财规划师|证券经纪|客户经理")


def text(job: dict) -> str:
    return f"{job.get('title', '')} {job.get('jd_text', '')}".lower()


def is_2027(job: dict) -> bool:
    hay = text(job)
    return any(k in hay for k in ("2027", "2027届", "27届", "27 届")) or "27届" in (job.get("tags") or [])


def tags(job: dict) -> set:
    return set(job.get("tags") or [])


def primary_role(job: dict) -> str:
    ts = tags(job)
    hay = text(job)
    if ts & {"AI产品", "策略产品", "产品", "决策支持"}:
        return "产品/策略"
    if ts & {"数据科学", "数据挖掘"} or re.search(r"数据分析|商业分析|数据产品|数据科学|数据挖掘", hay):
        return "数据"
    if "算法/ML" in ts:
        return "算法"
    if re.search(r"算法|机器学习|深度学习|数据挖掘|人工智能|大模型|llm|nlp|多模态", hay):
        return "算法"
    if re.search(r"经营分析|用户增长|产品运营|策略", hay):
        return "产品/策略"
    return "其他"


def is_internet(job: dict) -> bool:
    return job.get("industry") == "互联网/软件" or job.get("company_name") in BIG


def days_left(deadline: str) -> int | None:
    if not deadline or len(deadline) < 10:
        return None
    try:
        d = dt.date.fromisoformat(deadline[:10])
    except ValueError:
        return None
    return (d - dt.date.today()).days


def focus_score(job: dict) -> int:
    score = int(job.get("match_score") or 0)
    role = primary_role(job)
    hay = text(job)
    if is_2027(job):
        score += 60
    if role == "产品/策略":
        score += 90
    elif role == "数据":
        score += 70
    elif role == "算法":
        score += 20
    if is_internet(job) and role == "算法":
        score -= 70
    if not is_internet(job) and role in {"产品/策略", "数据"}:
        score += 25
    if any(k in hay for k in ("可转正", "转正", "留用", "return offer")):
        score += 18
    if any(k in hay for k in ("提前批", "秋招")):
        score += 12
    if WEAK.search(hay):
        score -= 120
    if LOW & tags(job):
        score -= 180
    if not job.get("deadline"):
        score -= 8
    return score


def base_score(job: dict) -> int:
    return int(job.get("match_score") or 0)


def is_focus_job(job: dict, min_focus: int, min_match: int) -> bool:
    if base_score(job) < min_match:
        return False
    role = primary_role(job)
    if role in {"产品/策略", "数据"}:
        return focus_score(job) >= min_focus
    if role == "算法":
        return focus_score(job) >= max(100, min_focus - 20)
    return focus_score(job) >= min_focus + 40


def clean_title(job: dict) -> str:
    title = re.sub(r"\s+", " ", str(job.get("title") or "")).strip()
    company = re.sub(r"\s+", " ", str(job.get("company_name") or "")).strip()
    if company and title.startswith(company):
        title = title[len(company):].strip(" -—·:：、，,")
    return title or company or "未命名岗位"


def deadline_text(job: dict) -> str:
    deadline = job.get("deadline") or "缺截止"
    d = days_left(job.get("deadline", ""))
    if d is None:
        return deadline
    if d == 0:
        return f"{deadline}，今天截止"
    if d > 0:
        return f"{deadline}，剩 {d} 天"
    return f"{deadline}，已过"


def line(job: dict) -> str:
    company = job.get("company_name") or "未知公司"
    role = primary_role(job)
    url = job.get("official_url") or ""
    link = f"\n  {url}" if url else ""
    return f"- {company}｜{clean_title(job)}\n  {role}｜匹配 {job.get('match_score', 0)}｜{deadline_text(job)}{link}"


def section(title: str, rows: list[dict], limit: int) -> list[str]:
    out = [f"## {title}"]
    if not rows:
        return out + ["- 暂无"]
    return out + [line(j) for j in pick_rows(rows, limit)]


def pick_rows(rows: list[dict], limit: int) -> list[dict]:
    """Pick display rows with a small company cap, matching section() output."""
    seen_company = Counter()
    picked = []
    for job in rows:
        c = job.get("company_name") or ""
        if seen_company[c] >= 2:
            continue
        picked.append(job)
        seen_company[c] += 1
        if len(picked) >= limit:
            break
    return picked


def inbox_count() -> int:
    if not os.path.exists(INBOX):
        return 0
    raw = open(INBOX, encoding="utf-8", errors="ignore").read()
    return len(re.findall(r"(?m)^牛客发现[:：]", raw))


def health_attention() -> int:
    if not os.path.exists(HEALTH):
        return 0
    try:
        report = json.load(open(HEALTH, encoding="utf-8"))
    except ValueError:
        return 0
    rows = report.get("sources", [])
    return sum(1 for r in rows if r.get("status") != "active" or r.get("alert") or r.get("last_error"))


def latest_first_seen(jobs: list[dict]) -> str:
    return max((j.get("first_seen") or "") for j in jobs if j.get("first_seen") is not None) if jobs else ""


def first_seen_day(job: dict) -> str:
    return str(job.get("first_seen") or "")[:10]


def job_key(job: dict) -> str:
    return str(job.get("dedup_key") or job.get("job_id") or job.get("official_url") or "")


def load_state(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {"version": 1, "pushed_keys": {}}
    try:
        state = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "pushed_keys": {}}
    if not isinstance(state.get("pushed_keys"), dict):
        state["pushed_keys"] = {}
    state.setdefault("version", 1)
    return state


def is_pushed(job: dict, state: dict) -> bool:
    key = job_key(job)
    return bool(key and key in state.get("pushed_keys", {}))


def mark_pushed(path: str, jobs: list[dict]) -> int:
    state = load_state(path)
    pushed = state.setdefault("pushed_keys", {})
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    added = 0
    for job in jobs:
        key = job_key(job)
        if not key or key in pushed:
            continue
        pushed[key] = {
            "pushed_at": now,
            "first_seen": job.get("first_seen") or "",
            "company": job.get("company_name") or "",
            "title": clean_title(job),
            "source_id": job.get("source_id") or "",
        }
        added += 1
    state["last_marked_at"] = now
    state["last_marked_count"] = added
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return added


def build(limit: int = 8, min_focus: int = 120, min_match: int = 50, mode: str = "new", since: str = "",
          include_existing_due: bool = False, state_path: str = STATE,
          ignore_state: bool = False, workbench_url: str = DEFAULT_WORKBENCH_URL) -> tuple[str, list[dict]]:
    jobs = json.load(open(JOBS, encoding="utf-8"))
    active = [j for j in jobs if not j.get("gone") and not (LOW & tags(j)) and not WEAK.search(text(j))]
    latest = latest_first_seen(active)
    since_day = since or (latest[:10] if latest else dt.date.today().isoformat())
    state = load_state(state_path) if state_path and not ignore_state else {"pushed_keys": {}}
    if mode == "all":
        pushed_pool = active
        scope_label = "全量预览"
        raw_new_count = len(pushed_pool)
        skipped_pushed = 0
    else:
        raw_pool = [j for j in active if first_seen_day(j) >= since_day]
        pushed_pool = [j for j in raw_pool if not is_pushed(j, state)]
        raw_new_count = len(raw_pool)
        skipped_pushed = raw_new_count - len(pushed_pool)
        scope_label = f"新增 since {since_day} · 未推送"

    c27_all = [j for j in active if is_2027(j)]
    c27_new = [j for j in pushed_pool if is_2027(j)]
    product_data = [j for j in c27_new if primary_role(j) in {"产品/策略", "数据"} and is_focus_job(j, min_focus, min_match)]
    non_internet = [j for j in c27_new if not is_internet(j) and primary_role(j) in {"产品/策略", "数据"} and is_focus_job(j, min_focus, min_match)]
    due_pool = active if (mode == "all" or include_existing_due) else pushed_pool
    due = [
        j for j in due_pool
        if (d := days_left(j.get("deadline", ""))) is not None
        and 0 <= d <= 7
        and is_focus_job(j, min_focus, min_match)
    ]
    missing = [j for j in c27_new if primary_role(j) in {"产品/策略", "数据"} and is_focus_job(j, min_focus, min_match) and not j.get("deadline")]

    product_data.sort(key=focus_score, reverse=True)
    non_internet.sort(key=focus_score, reverse=True)
    due.sort(key=lambda j: (days_left(j.get("deadline", "")) or 999, -focus_score(j)))
    missing.sort(key=focus_score, reverse=True)

    lines = [
        f"# Job Radar｜{dt.date.today().isoformat()} 新增机会",
        "",
        f"未推新增 {len(pushed_pool)} 条，其中 27届 {len(c27_new)} 条。",
        f"重点候选 {len(product_data)} 条；非互联网产品/数据 {len(non_internet)} 条；7天内截止 {len(due)} 条。",
    ]
    if skipped_pushed:
        lines.append(f"已自动过滤历史推送 {skipped_pushed} 条。")
    if workbench_url:
        lines.extend(["", f"信息台：{workbench_url}"])
    lines.extend([
        "",
        f"线索池：牛客待审核 {inbox_count()} 条；信源需关注 {health_attention()} 个。",
        "",
    ])
    selected: list[dict] = []
    sections = [
        ("新增优先看", product_data, limit),
        ("新增非互联网产品/数据", non_internet, limit),
        ("新增7天内截止" if mode != "all" and not include_existing_due else "7天内截止", due, limit),
        ("新增待补截止", missing, min(6, limit)),
    ]
    blocks = []
    for title, rows, section_limit in sections:
        picked = pick_rows(rows, section_limit)
        selected.extend(picked)
        blocks.append([f"## {title}"] + ([line(j) for j in picked] if picked else ["- 暂无"]))
    for block in blocks:
        lines.extend(block)
        lines.append("")
    unique_selected = {job_key(j): j for j in selected if job_key(j)}
    return "\n".join(lines), list(unique_selected.values())


def main() -> None:
    p = argparse.ArgumentParser(description="生成 Job Radar 自动化推送预览 Markdown。")
    p.add_argument("--out", default=OUT)
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--min-focus", type=int, default=120)
    p.add_argument("--min-match", type=int, default=50,
                   help="进入推送的最低原始匹配分，避免弱相关岗位靠规则加分混入")
    p.add_argument("--mode", choices=("new", "all"), default="new",
                   help="new=只推最近一次同步新增；all=全量预览")
    p.add_argument("--since", default="",
                   help="只在 mode=new 时生效，按 first_seen 日期 YYYY-MM-DD 过滤；默认最近 first_seen 日期")
    p.add_argument("--include-existing-due", action="store_true",
                   help="新增推送中也附带存量 7 天内截止岗位；默认不附带")
    p.add_argument("--state", default=STATE,
                   help="已推送状态文件；默认 data/notify_state.json")
    p.add_argument("--ignore-state", action="store_true",
                   help="忽略已推送状态，重新生成本范围新增预览")
    p.add_argument("--mark-pushed", action="store_true",
                   help="生成预览后，把本次预览实际列出的岗位标记为已推送；真实发送成功后再用")
    p.add_argument("--workbench-url", default=DEFAULT_WORKBENCH_URL,
                   help="推送中展示的在线工作台链接，例如 GitHub Pages URL")
    args = p.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    md, selected = build(args.limit, args.min_focus, args.min_match, args.mode, args.since,
                         args.include_existing_due, args.state, args.ignore_state,
                         args.workbench_url)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"✅ 推送预览已生成：{args.out}")
    if args.mark_pushed:
        added = mark_pushed(args.state, selected)
        print(f"✅ 已标记 {added} 条为已推送：{args.state}")


if __name__ == "__main__":
    main()
