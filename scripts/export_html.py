#!/usr/bin/env python3
"""把 data/jobs.json 导出成单页可浏览的 HTML（data/jobs.html）。

特点：
- 单文件、自带样式与脚本、数据内嵌，双击即可在浏览器打开（无需服务器）。
- 顶部统计 + 筛选：关键词搜索、类别(国家平台/高校/大厂官网/海外ATS)、地区、来源、最低分。
- 按匹配分/发布日期排序；岗位卡片含分数、薪资、地区、截止、风险标记、标签、原链接。

运行：python3 scripts/export_html.py    然后打开 data/jobs.html
"""
import html
import csv
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from job_radar import sync  # noqa: E402
from job_radar.normalize import normalize_salary  # noqa: E402
from job_radar.quality_rules import LOW_QUALITY_TAGS  # noqa: E402
from job_radar import workbench_rules as wr  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")


def build_records():
    with open(os.path.join(DATA_DIR, "jobs.json"), encoding="utf-8") as f:
        jobs = json.load(f)
    # source_id -> 友好名称
    name_map = {}
    try:
        for s in sync.read_sources():
            name_map[s["source_id"]] = s["company_name"]
    except Exception:  # noqa: BLE001
        pass
    def s(v):  # 统一转字符串（部分源的日期是 int 时间戳）
        return "" if v is None else str(v)

    import datetime as _dt
    def fmt_date(v):  # 兜底：纯数字 epoch(秒/毫秒) / 中文年月日 → YYYY-MM-DD
        t = s(v).strip()
        if "年" in t:  # 2026年06月22日 → 2026-06-22
            t = t.replace("年", "-").replace("月", "-").replace("日", "")
        if t.isdigit() and len(t) >= 10:
            n = int(t)
            if n > 1e12:
                n //= 1000
            try:
                t = _dt.datetime.utcfromtimestamp(n).strftime("%Y-%m-%d")
            except (ValueError, OSError):
                return ""
        t = t[:10]
        # 占位/脏日期（如 3000-01-01、9999-…）当作无截止，避免"剩 35 万天"
        if t[:4].isdigit() and int(t[:4]) >= 2090:
            return ""
        return t

    recs = []
    for j in jobs:
        if j.get("gone"):
            continue
        sid = j.get("source_id", "")
        sal_str = s(j.get("salary")) or s((j.get("extra") or {}).get("salary"))
        _, sx = normalize_salary(sal_str)
        pub = fmt_date(j.get("publish_time"))
        dl = fmt_date(j.get("deadline"))
        title = s(j.get("title"))
        jd = s(j.get("jd_text"))[:1200]
        kind = wr.kind(sid, title)
        stage = wr.stage(title, jd)
        c27 = wr.is_2027_cycle(sid, kind, title, jd, pub, stage)
        cat = wr.category(sid)
        recs.append({
            "id": s(j.get("dedup_key")) or s(j.get("job_id")),
            "sx": sx,                       # 归一化月薪上限（排序用，0=未知）
            "s": j.get("match_score", 0),
            "t": title,
            "c": s(j.get("company_name")),
            "loc": s(j.get("location")),
            "sal": sal_str,
            "src": name_map.get(sid, sid),
            "cat": cat,
            "kind": kind,
            "stage": stage,
            "cyc": "2027" if c27 else "",
            "conv": bool(any(k in title or k in jd.lower() for k in wr.CONVERT_KW)),
            "ind": wr.industry_display(s(j.get("industry"))),
            "gv": sid in ("gov-sasac", "gov-qyzp", "cn-iguopin"),   # 央国企核心源
            "bc": bool({"蓝领", "非目标岗"} & set(j.get("tags") or [])),  # 蓝领/专业不对口(默认隐藏)
            "lq": bool(LOW_QUALITY_TAGS & set(j.get("tags") or [])),
            "intern": ("实习" in s(j.get("title"))) or ("intern" in s(j.get("title")).lower()),
            "reg": wr.region_of(cat, s(j.get("location"))),
            "pub": pub,
            "dl": dl,
            "url": s(j.get("official_url")),
            "risk": j.get("risk_flags", []),
            "tags": j.get("tags", []),
            "jd": jd,
            "fs": s(j.get("first_seen")),
            "gone": bool(j.get("gone")),
            "group": "",
            "alts": [],
        })
    groups = defaultdict(list)
    for r in recs:
        if not r["gone"] and r["c"] and r["t"]:
            groups[(r["c"], r["t"])].append(r)
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: (-r["s"], r["reg"], r["loc"], r["id"]))
        gid = "g:" + rows[0]["id"]
        alts = [{"id": r["id"], "loc": r["loc"], "reg": r["reg"], "url": r["url"], "s": r["s"]}
                for r in rows]
        for r in rows:
            r["group"] = gid
            r["alts"] = alts
    recs.sort(key=lambda r: r["s"], reverse=True)
    return recs


def build_health():
    report_path = os.path.join(DATA_DIR, "health_report.json")
    state_path = os.path.join(DATA_DIR, "source_state.json")
    try:
        with open(report_path, encoding="utf-8") as f:
            report = json.load(f)
    except Exception:  # noqa: BLE001
        report = {}
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:  # noqa: BLE001
        state = {}
    source_meta = {s["source_id"]: s for s in sync.read_sources()}
    recent = {s.get("source_id"): s for s in report.get("sources", []) if s.get("source_id")}
    ids = sorted(set(source_meta) | set(state) | set(recent))
    sources = []
    for sid in ids:
        meta = source_meta.get(sid, {})
        st = dict(state.get(sid, {}))
        st.update(recent.get(sid, {}))
        skipped = bool(st.get("skipped")) or meta.get("status") in ("blocked", "deprecated")
        sources.append({
            "id": sid,
            "adapter": meta.get("adapter", st.get("adapter", "")),
            "status": st.get("status", meta.get("status", "")),
            "count": st.get("last_count", ""),
            "peak": st.get("peak_count", ""),
            "fails": st.get("consecutive_failures", 0),
            "ok": st.get("last_success_at", "")[:16].replace("T", " "),
            "err": st.get("last_error", ""),
            "alert": st.get("alert", ""),
            "skipped": skipped,
        })
    return {
        "generated_at": report.get("generated_at", ""),
        "store_total": report.get("store_total", 0),
        "new_this_run": report.get("new_this_run", 0),
        "sources": sources,
    }


def build_backlog():
    path = os.path.join(ROOT, "config", "source_backlog.csv")
    rows = []
    if not os.path.exists(path):
        return rows
    try:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append({k: (v or "").strip() for k, v in r.items()})
    except Exception:  # noqa: BLE001
        return []
    return rows


def build_inbox():
    """半自动导入池状态：只作为信息台线索，不混入正式岗位库。"""
    inbox_dir = os.path.join(DATA_DIR, "inbox")
    out = {
        "nowcoder_urls": 0,
        "nowcoder_blocks": 0,
        "inbox_files": 0,
        "review_html": False,
    }
    try:
        url_path = os.path.join(inbox_dir, "nowcoder_urls.txt")
        if os.path.exists(url_path):
            with open(url_path, encoding="utf-8", errors="ignore") as f:
                out["nowcoder_urls"] = len([ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")])
        feed_path = os.path.join(inbox_dir, "nowcoder_discovered.txt")
        if os.path.exists(feed_path):
            text = open(feed_path, encoding="utf-8", errors="ignore").read()
            out["nowcoder_blocks"] = len(re.findall(r"(?m)^牛客发现[:：]", text))
        if os.path.isdir(inbox_dir):
            out["inbox_files"] = len([n for n in os.listdir(inbox_dir) if not n.startswith(".")])
        out["review_html"] = os.path.exists(os.path.join(DATA_DIR, "import_preview_nowcoder.html"))
    except Exception:  # noqa: BLE001
        pass
    return out


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>招聘雷达工作台</title>
<style>
/* 莫兰迪 / 小红书 ins 风：冷调留白 · 低饱和鼠尾草绿点缀 */
:root{
  --ink:#30343b;--canvas:#ffffff;--fog:#f1f3f6;--ash:#6e747d;--graphite:#9aa0a9;
  --dove:#c4c9d0;--bd:#eceef1;--bd2:#e2e5ea;--clay:#6f9384;--clay-dk:#4f6f60;
  --peach:#e8efe9;--sage:#e9ecf4;--green:#5f8a6d;--red:#b06b74;
  --shadow:0 1px 2px rgba(40,45,55,.04),0 8px 24px -12px rgba(40,45,55,.12);
  --radius-card:18px;--radius-in:13px;--safe-top:env(safe-area-inset-top,0px);
}
*{box-sizing:border-box}
body{margin:0;color:var(--ink);
  background:radial-gradient(1200px 380px at 50% -200px,rgba(224,231,242,.55),rgba(255,255,255,0) 72%),#fafbfd;
  background-attachment:fixed;
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,"PingFang SC","Microsoft YaHei",sans-serif;
  letter-spacing:-.14px}
header{position:sticky;top:0;background:rgba(255,255,255,.88);backdrop-filter:blur(10px);
  border-bottom:1px solid var(--bd);padding:calc(16px + var(--safe-top)) 22px 16px;z-index:10}
h1{margin:0 0 4px;font-weight:600;font-size:24px;letter-spacing:-.5px;color:var(--ink)}
.stat{color:var(--graphite);font-size:12.5px}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;align-items:center}
input,select{background:var(--canvas);color:var(--ink);border:1px solid var(--bd2);
  border-radius:13px;padding:9px 13px;font-size:13px;outline:none;font-family:inherit}
input::placeholder{color:var(--dove)}
input:focus,select:focus{border-color:var(--ink)}
#q{flex:1;min-width:200px}
.chip{cursor:pointer;border:1px solid var(--bd2);background:var(--canvas);color:var(--graphite);
  border-radius:9999px;padding:6px 13px;font-size:12px;user-select:none;transition:.15s}
.chip:hover{border-color:var(--dove)}
.chip.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.range{display:flex;align-items:center;gap:6px;color:var(--graphite);font-size:12px}
main{max-width:1280px;margin:0 auto;padding:20px 22px;display:grid;
  grid-template-columns:repeat(auto-fill,minmax(min(360px,100%),1fr));gap:16px}
.card{background:var(--canvas);border-radius:var(--radius-card);padding:16px 18px;
  display:flex;flex-direction:column;gap:7px;box-shadow:var(--shadow);transition:.18s}
.card:hover{transform:translateY(-1px);box-shadow:0 0 0 1px rgba(4,23,43,.07),0 16px 30px -10px rgba(20,20,30,.16)}
.card.isgone{opacity:.55}
.card.t3{border-left:3px solid var(--clay)}
.card.t2{border-left:3px solid var(--dove)}
.card.t1{border-left:3px solid transparent}
.chead{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.ctitle{font-weight:500;font-size:15.5px;line-height:1.35;color:var(--ink)}
.cscore{flex:none;font-weight:500;font-size:13px;border-radius:9999px;padding:3px 11px;
  background:var(--fog);color:var(--ash)}
.cscore.t3{background:var(--peach);color:var(--clay-dk)}
.cco{color:var(--ash);font-size:13px}
.cmeta{color:var(--graphite);font-size:12.5px}
.cmeta .sal{color:var(--green)}
.ctime{color:var(--graphite);font-size:12px}
.dot{margin:0 6px;color:var(--dove)}
.creason{display:flex;flex-wrap:wrap;gap:5px;align-items:center}
.why{font-size:11px;color:var(--clay-dk);background:var(--peach);border-radius:9999px;padding:3px 9px}
.coach{border:1px solid var(--bd);background:#fbfcfb;border-radius:var(--radius-in);padding:9px 10px;
  color:var(--ash);font-size:12px;line-height:1.55}
.coach b{color:var(--ink);font-weight:600;margin-right:6px}.coach.hot{border-color:#d8e5dc;background:#f3f8f4}
.coach.warn{border-color:#f0d7d4;background:#fff8f6}.coach.muted{background:var(--fog)}
.b{font-size:11px;border-radius:9999px;padding:3px 9px;background:var(--fog);color:var(--graphite)}
.b.risk{background:#f6e7e3;color:var(--red)}
.b.src{background:var(--sage);color:#5b6477}
.b.new{background:var(--peach);color:var(--clay-dk)}
.b.gone{background:var(--fog);color:var(--dove)}
.b.k-c{background:#e3efe7;color:#3f6b52}
.b.k-i{background:#eef0f6;color:#5b6477}
.b.k-s{background:var(--fog);color:var(--graphite)}
.jdbox{white-space:pre-wrap;background:var(--fog);border:1px solid var(--bd);border-radius:var(--radius-in);
  padding:12px;color:var(--ash);font-size:12.5px;line-height:1.7;max-height:280px;overflow:auto;margin-top:4px}
.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.tab{cursor:pointer;border:1px solid transparent;background:transparent;color:var(--graphite);
  border-radius:9999px;padding:7px 14px;font-size:13px;user-select:none;transition:.15s}
.tab:hover{background:var(--fog)}
.tab.on{background:var(--ink);color:#fff}
.tab b{font-weight:500;opacity:.75;margin-left:4px}
.rtabs{margin-top:8px}
.rtabs .tab{font-size:12px;padding:5px 12px}
.rtabs .tab.on{background:var(--clay)}
.foot{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:3px}
.acts{display:flex;gap:6px;align-items:center}
.btn{cursor:pointer;background:var(--canvas);color:var(--ash);border:1px solid var(--bd2);
  border-radius:9999px;padding:5px 11px;font-size:12px;transition:.15s}
.btn:hover{border-color:var(--ink);color:var(--ink)}
.btn.hasnote{background:var(--peach);color:var(--clay-dk);border-color:#cfe0d6}
.jd{color:var(--graphite);font-size:12px;max-height:34px;overflow:hidden}
a.go{color:var(--clay-dk);text-decoration:none;font-size:12px;align-self:flex-start;font-weight:450}
a.go:hover{text-decoration:underline}
.empty{grid-column:1/-1;text-align:center;color:var(--graphite);padding:48px}
.cap{grid-column:1/-1;text-align:center;color:var(--graphite);font-size:12px;padding:10px}
.sal{color:var(--green)}
.dl{color:var(--ash)}
.dl.urgent{color:var(--red);font-weight:500}
.stsel{background:var(--canvas);color:var(--ash);border:1px solid var(--bd2);border-radius:9999px;
  padding:5px 11px;font-size:12px;cursor:pointer;outline:none;font-family:inherit}
.stsel.act{background:var(--peach);color:var(--clay-dk);border-color:#cfe0d6}
.notebox{width:100%;margin-top:7px;background:var(--fog);border:1px solid var(--bd2);
  border-radius:var(--radius-in);color:var(--ash);font:12.5px/1.6 inherit;padding:9px;
  resize:vertical;min-height:52px;outline:none}
.notebox:focus{border-color:var(--ink)}
/* 投递看板（横向列布局，覆盖 main 的网格） */
main.board{display:flex;gap:14px;overflow-x:auto;align-items:flex-start;padding-bottom:28px}
.bcol{background:var(--fog);border-radius:var(--radius-card);padding:12px;width:256px;min-width:256px;
  flex:none;display:flex;flex-direction:column;gap:9px}
.bcolh{font-weight:500;font-size:13px;color:var(--ink);padding-bottom:9px;border-bottom:1px solid var(--bd2)}
.bcolh b{color:var(--clay-dk);margin-left:4px}
.bcard{background:var(--canvas);border-radius:var(--radius-in);padding:10px 11px;box-shadow:var(--shadow)}
.bcard .bt{font-weight:500;font-size:12.5px;line-height:1.35;color:var(--ink)}
.bcard .bm{color:var(--graphite);font-size:11px;margin-top:5px;display:flex;flex-wrap:wrap;gap:6px}
.bnav{display:flex;gap:5px;margin-top:8px}
.bnav button,.bx{cursor:pointer;background:var(--canvas);color:var(--ash);border:1px solid var(--bd2);
  border-radius:9999px;padding:4px 6px;font-size:11px;transition:.15s}
.bnav button{flex:1}
.bnav button:hover,.bx:hover{border-color:var(--ink);color:var(--ink)}
.bempty{color:var(--dove);font-size:11px;text-align:center;padding:8px 0}
main.health{display:block;max-width:1180px}
.htable{width:100%;border-collapse:collapse;background:var(--canvas);box-shadow:var(--shadow);
  border-radius:var(--radius-card);overflow:hidden;font-size:12.5px}
.htable th,.htable td{padding:10px 12px;border-bottom:1px solid var(--bd);text-align:left;vertical-align:top}
.htable th{color:var(--ash);font-weight:500;background:var(--fog)}
.htable tr:last-child td{border-bottom:0}
.hbad{color:var(--red);font-weight:500}.hok{color:var(--green);font-weight:500}.hmuted{color:var(--graphite)}
/* 信息台 */
main.station{display:block;max-width:1240px}
.dash{display:grid;gap:16px}
.dashgrid{display:grid;grid-template-columns:1.3fr .9fr;gap:16px}
.dashrow{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.panel{background:var(--canvas);border:1px solid var(--bd);border-radius:var(--radius-card);padding:16px 18px;box-shadow:var(--shadow)}
.panel h2{margin:0 0 10px;font-size:15px;font-weight:600;letter-spacing:0;color:var(--ink)}
.metric{border:1px solid var(--bd);border-radius:var(--radius-in);padding:11px 12px;background:#fbfcfd;min-height:76px}
.metric b{display:block;font-size:23px;line-height:1.1;color:var(--ink);font-weight:650}
.metric span{display:block;color:var(--graphite);font-size:12px;margin-top:5px}
.slist{display:grid;gap:8px}.sjob{border:1px solid var(--bd);border-radius:var(--radius-in);padding:10px 11px;background:#fbfcfd}
.sjob .top{display:flex;justify-content:space-between;gap:10px}.sjob b{font-size:13px;font-weight:600}.sjob span{color:var(--graphite);font-size:12px}
.sjob .meta{margin-top:4px;color:var(--ash);font-size:12px}.sjob .act{color:var(--clay-dk);font-weight:600}
.sjob.task{border-left:3px solid var(--clay)}.sjob.task.people{border-left-color:#8b7b62}.sjob.task.data{border-left-color:#7186a8}
.barline{display:grid;grid-template-columns:82px 1fr 48px;gap:8px;align-items:center;margin:8px 0;color:var(--ash);font-size:12px}
.bartrack{height:8px;background:var(--fog);border-radius:999px;overflow:hidden}.barfill{height:100%;background:var(--clay);border-radius:999px}
.mini{display:flex;flex-wrap:wrap;gap:7px}.slink{cursor:pointer;border:1px solid var(--bd);background:#fbfcfd;color:var(--ash);border-radius:999px;padding:6px 10px;font-size:12px}
.slink:hover{border-color:var(--ink);color:var(--ink)}
.alertline{display:flex;justify-content:space-between;gap:10px;border-bottom:1px solid var(--bd);padding:7px 0;color:var(--ash);font-size:12px}
.alertline:last-child{border-bottom:0}.alertline b{color:var(--ink);font-weight:600}
.mutedline{color:var(--graphite);font-size:12px}
@media(max-width:900px){.dashgrid,.dashrow{grid-template-columns:1fr}}
@media(max-width:720px){
  body{background-attachment:scroll;font-size:13px}
  header{position:static;padding:12px 12px 10px}
  h1{font-size:20px}
  .filters,.tabs{flex-wrap:nowrap;overflow-x:auto;-webkit-overflow-scrolling:touch;
    scrollbar-width:none;margin-left:-2px;margin-right:-2px;padding:0 2px 2px}
  .filters::-webkit-scrollbar,.tabs::-webkit-scrollbar{display:none}
  #q{flex:0 0 260px;min-width:260px}
  select{flex:0 0 auto}
  .chip,.tab{flex:none}
  .range{flex:0 0 auto}
  main{padding:12px;grid-template-columns:1fr;gap:12px}
  .card,.panel{border-radius:14px;padding:13px}
  .dash{gap:12px}.dashgrid,.dashrow{gap:12px}
  main.board{padding-left:12px;padding-right:12px}
  .bcol{width:82vw;min-width:82vw}
  .htable{display:block;overflow-x:auto;white-space:nowrap}
}
</style></head><body>
<header>
  <h1>招聘雷达工作台 <span class="stat" id="gen"></span></h1>
  <div class="stat" id="summary"></div>
  <div class="filters">
    <input id="q" placeholder="限定专业 / 关键词匹配（空格分隔多词，搜 职位·公司·JD 要求）">
    <select id="sort"><option value="focus">按主攻优先</option><option value="s">按匹配分</option><option value="sx">按薪资</option><option value="dl">按截止日期</option><option value="pub">按发布日期</option><option value="fs">按入库时间</option></select>
    <span class="range">最低分 <input id="minScore" type="range" min="0" max="130" value="0" style="width:90px"> <b id="msv">0</b></span>
  </div>
  <div class="tabs" id="tabs"></div>
  <div class="tabs rtabs" id="rtabs"></div>
  <div class="filters" id="cats"></div>
  <div class="filters" id="inds"></div>
</header>
<main id="list"></main>
<script>
const DATA = __DATA__;
const HEALTH = __HEALTH__;
const BACKLOG = __BACKLOG__;
const INBOX = __INBOX__;
const GEN = "__GEN__";
const CATS = ["国聘","实习平台","群推送","国家平台","高校","大厂官网","海外ATS","其他"];
const REGION_ORDER = ["广东","浙江","江苏","上海","湖南","北京","远程/海外","其他"];
let fCat=new Set(), fInd=new Set(), fMin=0, fSort="focus", fQ="", tab="station", rtab="all";
const RENDER_CAP=400;
const MAXFS = DATA.reduce((m,r)=>r.fs>m?r.fs:m, "");  // 最新入库时间 = 本次新增
const groupKey=r=>r.group||r.id;
function compact(rows){
  const seen=new Set(), out=[];
  rows.forEach(r=>{const k=groupKey(r);if(seen.has(k))return;seen.add(k);out.push(r);});
  return out;
}
// 用户状态(收藏/忽略)存浏览器 localStorage，跨刷新保留
const SKEY="jobradar_status", NKEY="jobradar_notes";
let STATUS=JSON.parse(localStorage.getItem(SKEY)||"{}");
let NOTES=JSON.parse(localStorage.getItem(NKEY)||"{}");
for(const k in STATUS){if(STATUS[k]==="saved")STATUS[k]="interested";}  // 旧"收藏"→"感兴趣"
function setStatus(id,v){if(v)STATUS[id]=v;else delete STATUS[id];localStorage.setItem(SKEY,JSON.stringify(STATUS));}
function stOf(id){return STATUS[id]||"";}
function setNote(id,v){if(v)NOTES[id]=v;else delete NOTES[id];localStorage.setItem(NKEY,JSON.stringify(NOTES));}
function noteOf(id){return NOTES[id]||"";}
// 投递进度状态机：感兴趣→已投递→笔试→面试→Offer，旁路 已拒
const STAGES=[{k:"interested",label:"感兴趣"},{k:"applied",label:"已投递"},{k:"written",label:"笔试"},
              {k:"interview",label:"面试"},{k:"offer",label:"Offer"},{k:"rejected",label:"已拒"}];
const PIPELINE=new Set(STAGES.map(s=>s.k));
// 截止日期：与本机"今天"(本地时区)比较，算剩余天数；null=无截止/无法解析
function today(){const d=new Date();return new Date(d-d.getTimezoneOffset()*60000).toISOString().slice(0,10);}
function daysLeft(dl){if(!dl||dl.length<10)return null;
  const t=Date.parse(dl+"T00:00:00");if(isNaN(t))return null;
  return Math.round((t-Date.parse(today()+"T00:00:00"))/86400000);}
function expired(r){const d=daysLeft(r.dl);return d!=null&&d<0;}
const DUE_WINDOW=14;  // "即将截止" = 今天起 14 天内（含今天）
function dlSortKey(r){const d=daysLeft(r.dl);return d==null||d<0?99999:d;}  // 无/已过排末尾
function hasTag(r,t){return (r.tags||[]).includes(t);}
function hasAnyTag(r,arr){return arr.some(t=>hasTag(r,t));}
function convCandidate(r){const text=(r.t+" "+(r.jd||"")).toLowerCase();
  return r.conv||/可转正|转正|留用|return offer|长期实习|暑期实习|日常实习|实习生|青云计划/.test(text);}
function targetFit(r){return hasAnyTag(r,["产品","AI产品","策略产品","决策支持","算法/ML","数据科学","数据挖掘"])||/数据|产品|策略|商业分析|经营分析|战略|数字化|算法|机器学习|ai|大模型/i.test(r.t+" "+(r.jd||""));}
function manufacturingFit(r){return targetFit(r)&&!/机械|电气|操作|技工|工艺|设备|维修|采购|生产|质检|质量|仓储|外贸|医药代表|销售/.test(r.t);}
function isHunan(r){return /湖南|长沙|株洲|湘潭/.test((r.loc||"")+" "+(r.t||"")+" "+(r.jd||"")+" "+(r.src||""));}
function isConsumerCommerce(r){return r.ind==="消费/零售/快消"||/快消|消费|零售|电商|品牌|市场|用户增长|商业分析|产品运营|供应链|欧莱雅|宝洁|联合利华|安踏|李宁|名创|泡泡玛特|得物/.test((r.c||"")+" "+(r.t||"")+" "+(r.jd||""));}
function isInternet(r){return r.ind==="互联网/软件"||["腾讯","字节跳动","网易","京东","百度","快手","阿里","美团","拼多多"].includes(r.c);}
function primaryRole(r){
  if(hasAnyTag(r,["AI产品","策略产品","产品","决策支持"]))return "product";
  if(hasAnyTag(r,["数据科学","数据挖掘"]))return "data";
  if(hasTag(r,"算法/ML"))return "algo";
  if(/商业分析|经营分析|数据分析|数据产品|产品运营|用户增长|策略|产品/i.test(r.t+" "+(r.jd||"")))return "product_data";
  return "other";
}
function focusScore(r){
  let v=r.s||0;
  const role=primaryRole(r);
  const text=(r.t+" "+(r.jd||"")).toLowerCase();
  if(r.cyc==="2027")v+=60;
  if(role==="product")v+=90;
  if(role==="data")v+=70;
  if(role==="product_data")v+=60;
  if(role==="algo")v+=20;
  if(isInternet(r)&&role==="algo"&&!hasAnyTag(r,["产品","数据科学","数据挖掘","决策支持"]))v-=70;
  if(isInternet(r)&&role==="product")v+=10;
  if(!isInternet(r)&&["product","data","product_data"].includes(role))v+=25;
  if(convCandidate(r))v+=18;
  if(r.stage==="提前批"||r.stage==="秋招")v+=12;
  if(/机械|电气|材料|外贸|英语|市场营销|生产|设备|工艺|质检|质量|采购|销售|兼职|校园大使|大专|技术员/.test(text))v-=120;
  if(r.lq||r.bc)v-=180;
  if(!r.dl)v-=8;
  return v;
}
function fitLevel(r){
  if(r.lq||r.bc||/机械|电气|操作|技工|维修|质检|医药代表|电话销售|客户经理/.test(r.t))return "不适配";
  if(!r.url||!r.dl)return "信息不足";
  if(r.s>=85&&targetFit(r))return "强适配";
  if(r.s>=60||targetFit(r)||r.gv)return "可尝试";
  return "信息不足";
}
const MAIN_TABS=[{k:"station",label:"信息台"},{k:"c27",label:"27届主线"},{k:"nonnet",label:"非互联网"},
            {k:"convert",label:"转正候选"},{k:"hunan",label:"湖南/长沙"},
            {k:"product",label:"产品/策略"},{k:"algo",label:"算法/数据"},
            {k:"due",label:"即将截止"},{k:"board",label:"投递看板"},{k:"health",label:"信源健康"}];
const MORE_TABS=[{k:"advance",label:"提前批"},{k:"autumn",label:"秋招"},
            {k:"spring",label:"春招/补录"},{k:"summer",label:"暑期实习"},{k:"event",label:"宣讲/活动"},
            {k:"c27gov",label:"27届央企"},{k:"aipm",label:"AI产品"},{k:"strategy_pm",label:"策略产品"},
            {k:"decision",label:"决策支持"},{k:"datasci",label:"数据科学"},{k:"mining",label:"数据挖掘"},
            {k:"all",label:"全部(应届)"},{k:"xz",label:"校招"},{k:"intern",label:"实习"},
            {k:"social",label:"社招"},{k:"new",label:"新增"},{k:"hi",label:"高匹配"},
            {k:"needddl",label:"待补截止"},{k:"nourl",label:"缺链接"},{k:"quality",label:"质量风险"},
            {k:"gov",label:"央企招聘"},{k:"finance",label:"金融"},{k:"manufacturing",label:"制造硬件"},
            {k:"energy",label:"能源电力"},{k:"auto",label:"汽车新能源"},{k:"medical",label:"医药医疗"},
            {k:"consumer",label:"快消电商"},{k:"consulting",label:"咨询专业"},
            {k:"expired",label:"已过期"},{k:"ignored",label:"已忽略"}];
const TABS=[...MAIN_TABS,...MORE_TABS];
function healthAttentionCount(){
  return (HEALTH.sources||[]).filter(r=>r.status!=="active"||r.alert||r.err||r.skipped).length;
}
function predTab(r,k){const st=stOf(r.id);
  if(k==="station")return false;
  if(k==="health")return false;
  if(k==="ignored")return st==="ignored";
  if(k==="board")return PIPELINE.has(st);
  if(k==="expired")return !r.gone&&st!=="ignored"&&expired(r);
  if(k==="quality")return !r.gone&&st!=="ignored"&&!expired(r)&&(r.lq||r.bc);
  const base=!r.gone&&st!=="ignored"&&!r.bc&&!r.lq&&!expired(r); // 通用可见（非下线/忽略/蓝领/低质/过期）
  if(k==="c27")return base&&r.cyc==="2027";
  if(k==="nonnet")return base&&r.ind!=="互联网/软件"&&(r.cyc==="2027"||r.gv||r.cat==="国家平台"||r.cat==="高校");
  if(k==="advance")return base&&r.cyc==="2027"&&r.stage==="提前批";
  if(k==="autumn")return base&&r.cyc==="2027"&&r.stage==="秋招";
  if(k==="spring")return base&&r.cyc==="2027"&&r.stage==="春招/补录";
  if(k==="summer")return base&&r.cyc==="2027"&&r.stage==="暑期实习";
  if(k==="event")return base&&r.cyc==="2027"&&r.stage==="宣讲/活动";
  if(k==="convert")return base&&r.cyc==="2027"&&convCandidate(r);
  if(k==="c27gov")return base&&r.cyc==="2027"&&(r.gv||r.cat==="国家平台");
  if(k==="hunan")return base&&isHunan(r);
  if(k==="product")return base&&hasAnyTag(r,["产品","AI产品","策略产品","决策支持"]);
  if(k==="aipm")return base&&hasTag(r,"AI产品");
  if(k==="strategy_pm")return base&&hasTag(r,"策略产品");
  if(k==="decision")return base&&hasTag(r,"决策支持");
  if(k==="algo")return base&&(hasTag(r,"算法/ML")||hasAnyTag(r,["数据科学","数据挖掘"])||/数据分析|商业分析|数据产品|数据开发|数仓|数据仓库/i.test(r.t+" "+(r.jd||"")));
  if(k==="datasci")return base&&hasTag(r,"数据科学");
  if(k==="mining")return base&&hasTag(r,"数据挖掘");
  if(k==="social")return base&&r.kind==="社招";        // 社招单列
  const camp=base&&r.kind!=="社招";                    // 应届视图：剔除社招
  if(k==="xz")return camp&&r.kind==="校招";
  if(k==="intern")return camp&&r.kind==="实习";
  if(k==="due"){const d=daysLeft(r.dl);return camp&&d!=null&&d>=0&&d<=DUE_WINDOW;}
  if(k==="needddl")return camp&&r.cyc==="2027"&&!r.dl;
  if(k==="nourl")return camp&&!r.url;
  if(k==="new")return camp&&r.fs===MAXFS;
  if(k==="hi")return camp&&r.s>=80;
  if(k==="gov")return camp&&r.gv;
  if(k==="finance")return camp&&r.ind==="金融";
  if(k==="manufacturing")return camp&&(r.ind==="先进制造/工业"||r.ind==="半导体/电子"||r.ind==="新材料")&&manufacturingFit(r);
  if(k==="energy")return camp&&(r.ind==="能源/电力/石化"||r.ind==="化工");
  if(k==="auto")return camp&&r.ind==="汽车/新能源车";
  if(k==="medical")return camp&&r.ind==="医疗/医药";
  if(k==="consumer")return camp&&isConsumerCommerce(r);
  if(k==="consulting")return camp&&r.ind==="咨询/专业服务";
  return camp;}  // all = 应届相关(校招+实习+其他，默认不含社招/蓝领)
function renderTabs(){const box=document.getElementById("tabs");box.innerHTML="";
  MAIN_TABS.forEach(t=>{const n=t.k==="health"?healthAttentionCount():compact(DATA.filter(r=>predTab(r,t.k))).length;
    const c=el("span","tab"+(tab===t.k?" on":""),t.label+" <b>"+n+"</b>");
    c.onclick=()=>{tab=t.k;renderTabs();render();};box.appendChild(c);});
  renderRegionTabs();}
// 地区 Tab（单选，计数随当前视图 Tab 联动）
function renderRegionTabs(){const box=document.getElementById("rtabs");box.innerHTML="";
  if(tab==="station"||tab==="health"||tab==="board"){return;}
  const present=REGION_ORDER.filter(r=>DATA.some(x=>x.reg===r));
  ["all",...present].forEach(r=>{
    const n=compact(DATA.filter(x=>predTab(x,tab)&&(r==="all"||x.reg===r))).length;
    const c=el("span","tab"+(rtab===r?" on":""),(r==="all"?"全部地区":r)+" <b>"+n+"</b>");
    c.onclick=()=>{rtab=r;renderRegionTabs();render();};box.appendChild(c);});}
const el=(t,c,h)=>{const e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e;};
function chips(box,items,set){items.forEach(x=>{const c=el("span","chip",x);c.onclick=()=>{set.has(x)?set.delete(x):set.add(x);c.classList.toggle("on");render();};box.appendChild(c);});}
// 行业 chips：从数据里按出现次数动态生成（多到少）
const INDS=Object.entries(DATA.reduce((m,r)=>{m[r.ind]=(m[r.ind]||0)+1;return m;},{}))
  .sort((a,b)=>b[1]-a[1]).map(x=>x[0]);
chips(document.getElementById("cats"),CATS,fCat);
chips(document.getElementById("inds"),INDS,fInd);
document.getElementById("q").oninput=e=>{fQ=e.target.value.trim().toLowerCase();render();};
document.getElementById("sort").onchange=e=>{fSort=e.target.value;render();};
document.getElementById("minScore").oninput=e=>{fMin=+e.target.value;document.getElementById("msv").textContent=fMin;render();};
document.getElementById("gen").textContent="· 生成于 "+GEN;
function esc(s){return (s||"").replace(/[&<>]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));}
// 把打分信号 tag 讲成人话（推荐理由）；技术标签单列
const SIG={role_match:"岗位匹配",industry_match:"目标行业",city_match:"目标城市",
           "大厂":"大厂","硬科技":"硬科技","外企":"外企在华","央国企":"央国企",
           "产品":"产品岗","AI产品":"AI产品","策略产品":"策略产品","决策支持":"决策支持",
           "算法/ML":"算法/ML","数据科学":"数据科学","数据挖掘":"数据挖掘"};
const QTAG=new Set(["代招/委托","猎头","劳务派遣","泛销售","低相关管培","地点风险","缺官网链接"]);
function reason(r){return (r.tags||[]).filter(t=>SIG[t]).map(t=>SIG[t]);}
function techTags(r){return (r.tags||[]).filter(t=>!t.startsWith("行业:")&&!SIG[t]&&t!=="offshore");}
function coach(r){
  const d=daysLeft(r.dl), q=r.lq||r.bc, missing=!r.url||!r.dl;
  if(q)return {cls:"warn",label:"暂跳过",text:"质量风险较高，除非公司/岗位特别确定，否则不进入主投递队列。"};
  if(expired(r))return {cls:"muted",label:"已过期",text:"截止已过，适合只做公司/岗位参考。"};
  if(!r.url)return {cls:"warn",label:"先补链接",text:"没有官网或投递链接，先核验来源再投入时间。"};
  if(r.s>=90&&r.cyc==="2027"&&d!=null&&d<=7)return {cls:"hot",label:"今天优先投",text:"27届高匹配且截止很近，适合放进今日投递清单。"};
  if(r.s>=80&&r.cyc==="2027")return {cls:"hot",label:"重点跟进",text:"27届主线高匹配，建议加入投递看板并补齐截止/网申状态。"};
  if(r.s>=70&&(hasAnyTag(r,["产品","AI产品","策略产品","决策支持","算法/ML","数据科学","数据挖掘"])||r.gv))return {cls:"hot",label:"值得看",text:"方向或雇主层级贴近目标，可以快速判断 JD 后决定是否投递。"};
  if(missing)return {cls:"muted",label:"补信息",text:"信息不完整，先看原文或等后续更新。"};
  return {cls:"muted",label:"观察",text:"匹配度一般，适合放在备选池，不抢占高优先级投递时间。"};
}
function secMatch(r){  // 次级筛选（最低分/类别/地区/行业/搜索），与 Tab 正交
  if(fMin&&r.s<fMin)return false;
  if(fCat.size&&!fCat.has(r.cat))return false;
  if(rtab!=="all"&&r.reg!==rtab)return false;
  if(fInd.size&&!fInd.has(r.ind))return false;
  if(fQ){const hay=(r.t+" "+r.c+" "+(r.jd||"")+" "+(r.tags||[]).join(" ")).toLowerCase();
    // 多关键词空格分隔=与逻辑(都要命中)，支持"数据 SQL"这种专业/关键词限定
    if(!fQ.split(/\s+/).every(w=>hay.includes(w)))return false;}
  return true;
}
function match(r){return predTab(r,tab)&&secMatch(r);}
function diversifyRows(rows){
  if(rows.length<8)return rows;
  const arr=rows.slice();
  const out=[];
  while(arr.length){
    const cand=arr.shift();
    const c=cand.c||"";
    const run=out.slice(-2).filter(x=>(x.c||"")===c).length;
    if(run>=2){
      const base=focusScore(cand);
      const altIdx=arr.findIndex(x=>(x.c||"")!==c && base-focusScore(x)<=55);
      if(altIdx>=0){
        out.push(arr.splice(altIdx,1)[0]);
        arr.unshift(cand);
        continue;
      }
    }
    out.push(cand);
  }
  return out;
}
function render(){
  const list=document.getElementById("list");
  if(tab==="station"){renderStation();return;}
  if(tab==="board"){list.classList.add("board");renderBoard();return;}
  if(tab==="health"){renderHealth();return;}
  list.classList.remove("board");
  list.classList.remove("health");
  let rows=compact(DATA.filter(match));
  const sk=tab==="due"?"dl":fSort;  // 即将截止 Tab 默认按最近截止排
  rows.sort((a,b)=>sk==="pub"?(b.pub||"").localeCompare(a.pub||"")
    :sk==="fs"?(b.fs||"").localeCompare(a.fs||"")
    :sk==="dl"?dlSortKey(a)-dlSortKey(b)
    :sk==="sx"?(b.sx||0)-(a.sx||0)
    :sk==="focus"?focusScore(b)-focusScore(a):b.s-a.s);
  if(sk==="focus")rows=diversifyRows(rows);
  list.innerHTML="";
  const visibleBase=compact(DATA.filter(r=>predTab(r,"all"))).length;
  const c27N=compact(DATA.filter(r=>predTab(r,"c27"))).length;
  const advN=compact(DATA.filter(r=>predTab(r,"advance"))).length;
  const autumnN=compact(DATA.filter(r=>predTab(r,"autumn"))).length;
  const springN=compact(DATA.filter(r=>predTab(r,"spring"))).length;
  const prodN=compact(DATA.filter(r=>predTab(r,"product"))).length;
  const decN=compact(DATA.filter(r=>predTab(r,"decision"))).length;
  const algoN=compact(DATA.filter(r=>predTab(r,"algo"))).length;
  const needDdl=compact(DATA.filter(r=>predTab(r,"needddl"))).length;
  const qN=compact(DATA.filter(r=>predTab(r,"quality"))).length;
  const noUrl=compact(DATA.filter(r=>predTab(r,"nourl"))).length;
  const expiredN=compact(DATA.filter(r=>predTab(r,"expired"))).length;
  const nodl=DATA.filter(r=>!r.gone&&!r.dl).length;
  const grouped=DATA.filter(r=>r.group).length-compact(DATA.filter(r=>r.group)).length;
  const sortHint=sk==="focus"?" · 当前按主攻排序+温和去簇：产品/策略/数据优先，避免同公司刷屏":"";
  document.getElementById("summary").textContent=`在架 ${DATA.length} 条，当前筛选 ${rows.length} 条 · 27届 ${c27N} 条（提前批 ${advN} / 秋招 ${autumnN} / 春招补录 ${springN}） · 产品岗 ${prodN} 条 · 算法/ML ${algoN} 条 · 决策支持 ${decN} 条 · 质量风险 ${qN} 条 · 待补截止 ${needDdl} 条 · 缺链接 ${noUrl} 条 · 已隐藏过期 ${expiredN} 条 · 多城市折叠 ${grouped} 条${sortHint}`;
  if(!rows.length){list.appendChild(el("div","empty","没有匹配的岗位，放宽筛选试试"));return;}
  rows.slice(0,RENDER_CAP).forEach(r=>{
    const tier=r.s>=80?"t3":r.s>=50?"t2":"t1";
    const card=el("div","card "+tier+(r.gone?" isgone":""));
    // 标题（去掉与公司名重复的前缀）
    let dt=r.t;
    if(r.c && dt.indexOf(r.c)===0) dt=dt.slice(r.c.length).replace(/^[\s\-—·:：、，,]+/,"");
    const titleText=dt||r.c;
    let pre="";
    const KC={"实习":"k-i","校招":"k-c","社招":"k-s"};
    if(r.cyc==="2027")pre+='<span class="b k-c">27届</span> ';
    if(r.stage&&r.stage!=="其他")pre+='<span class="b">'+esc(r.stage)+'</span> ';
    if(r.conv)pre+='<span class="b k-i">可转正</span> ';
    if(KC[r.kind])pre+='<span class="b '+KC[r.kind]+'">'+r.kind+'</span> ';
    if(r.fs===MAXFS&&!r.gone)pre+='<span class="b new">新增</span> ';
    if(r.gone)pre+='<span class="b gone">已下线</span> ';
    const head=el("div","chead");
    head.appendChild(el("div","ctitle",pre+esc(titleText)));
    head.appendChild(el("div","cscore "+tier,r.s));
    card.appendChild(head);
    // 公司 / 信息 / 时间
    if(r.c && titleText!==r.c) card.appendChild(el("div","cco",esc(r.c)));
    const info=[];
    const place=r.loc||r.reg; if(place)info.push(esc(place));
    if(r.ind)info.push(esc(r.ind));
    if(r.sal)info.push('<span class="sal">'+esc(r.sal)+'</span>');
    if(info.length)card.appendChild(el("div","cmeta",info.join('<span class="dot">·</span>')));
    if(r.alts&&r.alts.length>1){
      const cities=[...new Set(r.alts.map(a=>a.loc||a.reg).filter(Boolean))];
      card.appendChild(el("div","cmeta","同岗多城市："+cities.slice(0,8).map(esc).join(" / ")+(cities.length>8?" 等":"")));
    }
    const tm=[];
    if(r.pub)tm.push("发布 "+r.pub);
    if(r.dl){const d=daysLeft(r.dl);
      const lab=d==null?"":d<0?"（已过）":d===0?"（今天截止）":"（剩 "+d+" 天）";
      const urgent=d!=null&&d>=0&&d<=3;
      tm.push('<span class="dl'+(urgent?' urgent':'')+'">截止 '+r.dl+lab+'</span>');}
    if(tm.length)card.appendChild(el("div","ctime",tm.join('<span class="dot">·</span>')));
    // 推荐理由 + 技术标签 + 风险
    const rs=reason(r), tech=techTags(r);
    let rh="";
    if(rs.length)rh+='<span class="why">'+rs.join(" · ")+'</span>';
    tech.slice(0,6).forEach(t=>rh+='<span class="b">'+esc(t)+'</span>');
    (r.tags||[]).filter(t=>QTAG.has(t)).slice(0,4).forEach(t=>rh+='<span class="b risk">'+esc(t)+'</span>');
    (r.risk||[]).forEach(t=>rh+='<span class="b risk">'+esc(t)+'</span>');
    if(rh){const cr=el("div","creason");cr.innerHTML=rh;card.appendChild(cr);}
    const adv=coach(r);
    card.appendChild(el("div","coach "+adv.cls,"<b>"+esc(adv.label)+"</b>"+esc(adv.text)));
    // 底部：查看要求(JD 内联展开) / 原岗位 / 备注
    const foot=el("div","foot"), left=el("div","acts");
    let jb=null;
    if(r.jd){
      jb=el("div","jdbox");jb.style.display="none";jb.textContent=r.jd;
      const tg=el("button","btn","查看要求 ▾");
      tg.onclick=()=>{const open=jb.style.display==="none";jb.style.display=open?"block":"none";tg.textContent=open?"收起 ▴":"查看要求 ▾";};
      left.appendChild(tg);
    }
    if(r.url){const a=el("a","go","原岗位 ↗");a.href=r.url;a.target="_blank";left.appendChild(a);}
    // 每岗备注（自动存本地，跨刷新保留）
    const note=noteOf(r.id);
    const nbox=el("textarea","notebox");nbox.style.display="none";nbox.value=note;
    nbox.placeholder="投递备注（如：网申已交 / 笔试 6.25 / 一面挂…，自动保存）";
    nbox.oninput=()=>setNote(r.id,nbox.value.trim());
    const nbtn=el("button","btn"+(note?" hasnote":""),note?"备注 *":"备注");
    nbtn.onclick=()=>{const open=nbox.style.display==="none";nbox.style.display=open?"block":"none";if(open)nbox.focus();};
    left.appendChild(nbtn);
    foot.appendChild(left);
    // 投递进度下拉：把岗位移入流水线 / 忽略
    const stv=stOf(r.id);
    const acts=el("div","acts");
    const sel=el("select","stsel"+(PIPELINE.has(stv)?" act":""));
    sel.innerHTML='<option value="">＋ 加入投递</option>'
      +STAGES.map(s=>'<option value="'+s.k+'">'+s.label+'</option>').join('')
      +'<option value="ignored">✕ 忽略</option>';
    sel.value=stv;
    sel.onchange=()=>{setStatus(r.id,sel.value);renderTabs();render();};
    acts.appendChild(sel);foot.appendChild(acts);
    card.appendChild(foot);
    if(jb)card.appendChild(jb);
    card.appendChild(nbox);
    list.appendChild(card);
  });
  if(rows.length>RENDER_CAP)list.appendChild(el("div","cap",`仅显示前 ${RENDER_CAP} 条（共 ${rows.length} 条），请用搜索/筛选缩小范围`));
}
// ===== 信息台 =====
function pct(n,d){return d?Math.round(n*100/d):0;}
function topRows(rows,keyFn,limit=6){
  const m=new Map();rows.forEach(r=>{const k=keyFn(r);if(k)m.set(k,(m.get(k)||0)+1);});
  return [...m.entries()].sort((a,b)=>b[1]-a[1]).slice(0,limit);
}
function switchTab(k){tab=k;renderTabs();render();}
function actionRank(r){
  const d=daysLeft(r.dl);
  const fs=focusScore(r);
  if(r.s>=90&&r.cyc==="2027"&&d!=null&&d>=0&&d<=7)return 500-d;
  if(r.cyc==="2027"&&fs>=190)return 400+fs;
  if(r.s>=75&&(r.gv||hasAnyTag(r,["AI产品","策略产品","决策支持","数据科学","数据挖掘","产品"])))return 300+fs;
  if(d!=null&&d>=0&&d<=3)return 260-d;
  return fs;
}
function taskList(all,c27,due,needddl,quality,sourceBad){
  const out=[];
  const hot=all.filter(r=>actionRank(r)>=300).sort((a,b)=>actionRank(b)-actionRank(a)).slice(0,3);
  hot.forEach(r=>{
    const adv=coach(r);let dt=r.t;if(r.c&&dt.indexOf(r.c)===0)dt=dt.slice(r.c.length).replace(/^[\\s\\-—·:：、，,]+/,"");
    const d=daysLeft(r.dl);const dl=r.dl?(d==null?r.dl:d<0?r.dl+" 已过":r.dl+" 剩 "+d+" 天"):"缺截止";
    out.push({kind:"投递", cls:"task", title:dt||r.c, meta:`${r.c} · ${r.stage||r.kind} · ${r.reg} · ${dl}`, action:`${adv.label}：${adv.text}`, score:r.s});
  });
  const missing=needddl.filter(r=>r.s>=70).slice(0,2);
  missing.forEach(r=>out.push({kind:"补信息", cls:"task data", title:r.c||r.t, meta:"缺截止或关键信息", action:"先去官网、公众号原文、学校群截图里补截止；补不上就降级为观察。", score:r.s}));
  if(sourceBad>0)out.push({kind:"修信源", cls:"task data", title:"检查异常信源", meta:`${sourceBad} 个源需要关注`, action:"看信源健康：区分接口失效、DNS/网络、登录墙、临时 0 条，别把失败当作没有机会。", score:sourceBad});
  out.push({kind:"问人", cls:"task people", title:"找 2 个非互联网信源", meta:"同学/学长姐/就业办/学院群/宣讲会", action:"问：有没有 27届提前批、内推码、线下宣讲、企业微信群或未公开表格。", score:""});
  out.push({kind:"导入", cls:"task people", title:"整理群消息和公众号", meta:"把人传人的信息放进系统", action:"今天看到的学校群、牛客帖、公众号，用导入审核台过一遍，不要只等公开网页。", score:""});
  return out.slice(0,8);
}
function intelligenceState(){
  const reviewed=DATA.filter(r=>r.source_id==="feed-nowcoder"||r.src==="牛客内推帖").length;
  return [
    {k:"已确认岗位", n:compact(DATA.filter(r=>predTab(r,"all"))).length, note:"进入主库，可投递/跟进"},
    {k:"待审核线索", n:INBOX.nowcoder_blocks||0, note:"牛客/讨论帖，只是线索池"},
    {k:"牛客URL", n:INBOX.nowcoder_urls||0, note:"待打开原帖核验"},
    {k:"审核台", n:INBOX.review_html?"已生成":"未生成", note:"审核后才入库"},
  ];
}
function renderStation(){
  const list=document.getElementById("list");list.innerHTML="";
  list.classList.remove("board");list.classList.remove("health");list.classList.add("station");
  const all=compact(DATA.filter(r=>predTab(r,"all")));
  const c27=compact(DATA.filter(r=>predTab(r,"c27")));
  const nonnet=compact(DATA.filter(r=>predTab(r,"nonnet")));
  const internet=all.filter(r=>r.ind==="互联网/软件");
  const due=compact(DATA.filter(r=>predTab(r,"due")));
  const quality=compact(DATA.filter(r=>predTab(r,"quality")));
  const needddl=compact(DATA.filter(r=>predTab(r,"needddl")));
  const sourceBad=healthAttentionCount();
  const tasks=taskList(all,c27,due,needddl,quality,sourceBad);
  const fitCounts=topRows(all,r=>fitLevel(r),4);
  const unchecked=INBOX.nowcoder_blocks||0;
  document.getElementById("summary").textContent=`信息台：已确认 ${all.length} · 27届 ${c27.length} · 待审核线索 ${unchecked} · 非互联网 ${nonnet.length} · 今日动作 ${tasks.length}`;
  const wrap=el("div","dash");
  const metrics=el("section","dashrow");
  [["已确认岗位",all.length,"来自正式库，可投递跟进"],["待审核线索",unchecked,"牛客/群/公众号先核验"],["27届主线",c27.length,"提前批/秋招/春招/实习"],["今日动作",tasks.length,"投递、补信息、问人、导入"]].forEach(x=>{
    const m=el("div","metric",`<b>${x[1]}</b><span>${x[0]} · ${x[2]}</span>`);metrics.appendChild(m);
  });
  wrap.appendChild(metrics);
  const grid=el("div","dashgrid");
  const left=el("section","panel");left.innerHTML="<h2>今日指挥台</h2>";
  const sl=el("div","slist");
  tasks.forEach(t=>{
    const node=el("article","sjob "+t.cls,`<div class="top"><b>${esc(t.kind)}｜${esc(t.title)}</b><span>${esc(String(t.score||""))}</span></div>
      <div class="meta">${esc(t.meta)}</div>
      <div class="meta act">${esc(t.action)}</div>`);
    sl.appendChild(node);
  });
  left.appendChild(sl);grid.appendChild(left);
  const right=el("section","panel");right.innerHTML="<h2>线索漏斗</h2>";
  intelligenceState().forEach(x=>right.appendChild(el("div","alertline",`<b>${esc(x.k)}</b><span>${esc(String(x.n))}</span>`)));
  right.appendChild(el("div","mutedline","信息台口径：待审核线索不等于岗位。先核公司、岗位、截止、官网链接，再进入主库。"));
  right.appendChild(el("h2",null,"快捷入口"));
  const quick=el("div","mini");
  [["转正候选","convert"],["湖南/长沙","hunan"],["非互联网","nonnet"],["央企招聘","gov"],["金融","finance"],["制造硬件(谨慎)","manufacturing"],["能源电力","energy"],["汽车新能源","auto"],["医药医疗","medical"],["快消电商","consumer"],["咨询专业","consulting"],["待补截止","needddl"],["信源健康","health"]].forEach(([label,k])=>{
    const b=el("button","slink",label);b.onclick=()=>switchTab(k);quick.appendChild(b);
  });
  right.appendChild(quick);
  right.appendChild(el("h2",null,"信息缺口"));
  const gaps=el("div",null,`<div class="alertline"><b>待补截止</b><span>${needddl.length}</span></div>
    <div class="alertline"><b>质量风险</b><span>${quality.length}</span></div>
    <div class="alertline"><b>缺链接</b><span>${compact(DATA.filter(r=>predTab(r,"nourl"))).length}</span></div>
    <div class="alertline"><b>信源异常</b><span>${sourceBad}</span></div>`);
  right.appendChild(gaps);grid.appendChild(right);wrap.appendChild(grid);
  const grid2=el("div","dashgrid");
  const fit=el("section","panel");fit.innerHTML="<h2>适配分层</h2>";
  fitCounts.forEach(([k,n])=>fit.appendChild(el("div","barline",`<span>${esc(k)}</span><div class="bartrack"><div class="barfill" style="width:${pct(n,all.length)}%"></div></div><span>${n}</span>`)));
  fit.appendChild(el("div","mutedline","参考 Huntr/个人求职 tracker 的做法：先分清强适配、可尝试、信息不足、不适配，再决定投递动作。"));
  grid2.appendChild(fit);
  const stage=el("section","panel");stage.innerHTML="<h2>27届节点</h2>";
  const stages=[["提前批","advance"],["秋招","autumn"],["春招/补录","spring"],["暑期实习","summer"],["宣讲/活动","event"],["可转正","convert"]];
  stages.forEach(([label,k])=>{const n=compact(DATA.filter(r=>predTab(r,k))).length;
    stage.appendChild(el("div","barline",`<span>${label}</span><div class="bartrack"><div class="barfill" style="width:${pct(n,c27.length)}%"></div></div><span>${n}</span>`));});
  grid2.appendChild(stage);wrap.appendChild(grid2);
  const gridRole=el("div","dashgrid");
  const roles=el("section","panel");roles.innerHTML="<h2>方向热度</h2>";
  [["产品岗","product"],["AI产品","aipm"],["策略产品","strategy_pm"],["决策支持","decision"],["算法/ML","algo"],["数据科学","datasci"],["数据挖掘","mining"]].forEach(([label,k])=>{
    const n=compact(DATA.filter(r=>predTab(r,k))).length;
    roles.appendChild(el("div","barline",`<span>${label}</span><div class="bartrack"><div class="barfill" style="width:${pct(n,Math.max(1,c27.length))}%"></div></div><span>${n}</span>`));});
  gridRole.appendChild(roles);
  const miss=el("section","panel");miss.innerHTML="<h2>缺口雷达</h2>";
  const gaps2=[
    ["湖南转正候选", compact(DATA.filter(r=>predTab(r,"hunan")&&predTab(r,"convert"))).length],
    ["非互联网转正", compact(DATA.filter(r=>predTab(r,"nonnet")&&predTab(r,"convert"))).length],
    ["快消电商 27届", compact(DATA.filter(r=>predTab(r,"consumer")&&r.cyc==="2027")).length],
    ["金融 27届", compact(DATA.filter(r=>predTab(r,"finance")&&r.cyc==="2027")).length],
    ["咨询专业 27届", compact(DATA.filter(r=>predTab(r,"consulting")&&r.cyc==="2027")).length],
    ["制造硬件强适配", compact(DATA.filter(r=>predTab(r,"manufacturing")&&fitLevel(r)==="强适配")).length],
  ];
  gaps2.forEach(([label,n])=>miss.appendChild(el("div","alertline",`<b>${esc(label)}</b><span>${n}</span>`)));
  miss.appendChild(el("div","mutedline","参考 ATS 漏斗/来源报表：不仅看已有数量，也看哪些组合明显缺样本。"));
  gridRole.appendChild(miss);wrap.appendChild(gridRole);
  const grid3=el("div","dashgrid");
  const non=el("section","panel");non.innerHTML="<h2>非互联网行业雷达</h2>";
  [["央企招聘","gov"],["金融","finance"],["制造硬件(适配后)","manufacturing"],["能源电力","energy"],["汽车新能源","auto"],["医药医疗","medical"],["快消电商","consumer"],["咨询专业","consulting"],["湖南/长沙","hunan"]].forEach(([label,k])=>{
    const n=compact(DATA.filter(r=>predTab(r,k))).length;
    non.appendChild(el("div","barline",`<span>${label}</span><div class="bartrack"><div class="barfill" style="width:${pct(n,Math.max(1,nonnet.length))}%"></div></div><span>${n}</span>`));});
  non.appendChild(el("div","mutedline","这里故意把互联网拆出去看：如果非互联网数量太低，优先补官网/就业办/线下宣讲/内推表格。"));
  grid3.appendChild(non);
  const src=el("section","panel");src.innerHTML="<h2>信息来源雷达</h2>";
  topRows(all,r=>r.cat,8).forEach(([k,n])=>src.appendChild(el("div","barline",`<span>${esc(k)}</span><div class="bartrack"><div class="barfill" style="width:${pct(n,all.length)}%"></div></div><span>${n}</span>`)));
  const nk=DATA.filter(r=>(r.src||"").includes("牛客")||(r.id||"").includes("nk-")||(r.cat==="实习平台"&&/nowcoder/i.test(r.url||"")));
  src.appendChild(el("div","alertline",`<b>牛客职位中心</b><span>${compact(nk).length} 已入库</span>`));
  src.appendChild(el("div","alertline",`<b>牛客讨论/内推</b><span>${INBOX.nowcoder_blocks||0} 待审核</span>`));
  src.appendChild(el("div","alertline",`<b>导入审核台</b><span>${INBOX.review_html?"可打开":"待生成"}</span>`));
  src.appendChild(el("div","mutedline","公开互联网只是来源之一；讨论帖只能算情报，审核通过才进入正式岗位。学校群、就业办、宣讲会、学长姐和内推表格要并行补。"));
  grid3.appendChild(src);wrap.appendChild(grid3);
  const grid4=el("div","dashgrid");
  const reg=el("section","panel");reg.innerHTML="<h2>地区分布</h2>";
  topRows(c27,r=>r.reg,8).forEach(([k,n])=>reg.appendChild(el("div","barline",`<span>${esc(k)}</span><div class="bartrack"><div class="barfill" style="width:${pct(n,c27.length)}%"></div></div><span>${n}</span>`)));
  grid4.appendChild(reg);
  const gap=el("section","panel");gap.innerHTML="<h2>当前结构偏差</h2>";
  gap.appendChild(el("div","alertline",`<b>互联网/软件</b><span>${internet.length} / ${all.length}</span>`));
  gap.appendChild(el("div","alertline",`<b>非互联网 27届</b><span>${nonnet.length}</span>`));
  gap.appendChild(el("div","alertline",`<b>腾讯/字节/网易/京东</b><span>${all.filter(r=>["腾讯","字节跳动","网易","京东"].includes(r.c)).length}</span>`));
  gap.appendChild(el("div","mutedline","这不是说互联网不能投，而是提醒不要让互联网样本支配全部判断。"));
  grid4.appendChild(gap);wrap.appendChild(grid4);
  const grid5=el("div","dashgrid");
  const backlog=el("section","panel");backlog.innerHTML="<h2>待攻信源</h2>";
  const bl=(BACKLOG||[]).filter(x=>["1","2"].includes(String(x.priority))).slice(0,10);
  bl.forEach(x=>backlog.appendChild(el("div","alertline",`<b>${esc(x.name||x.source_id)}</b><span>${esc(x.status||"")}</span>`)));
  backlog.appendChild(el("div","mutedline","这里对应 source_backlog.csv：不是没有机会，而是哪些金融/快消/咨询/制造源还没接入或需要人工导入。"));
  grid5.appendChild(backlog);
  const methods=el("section","panel");methods.innerHTML="<h2>信息台结构</h2>";
  methods.appendChild(el("div","alertline","<b>信源层</b><span>官网 / 高校 / 国聘 / 群 / 牛客</span>"));
  methods.appendChild(el("div","alertline","<b>审核层</b><span>公司、岗位、截止、链接、适配度</span>"));
  methods.appendChild(el("div","alertline","<b>行动层</b><span>今天投递 / 补信息 / 问人 / 暂跳过</span>"));
  methods.appendChild(el("div","mutedline","1.0 的重点不是抓全网，而是把情报变成可执行状态：确认、待核、缺口、下一步。"));
  grid5.appendChild(methods);wrap.appendChild(grid5);
  list.appendChild(wrap);
}
// ===== 投递看板 =====
function boardCard(r,stg){
  const c=el("div","bcard");
  let dt=r.t; if(r.c&&dt.indexOf(r.c)===0)dt=dt.slice(r.c.length).replace(/^[\s\-—·:：、，,]+/,"");
  c.appendChild(el("div","bt",esc(dt||r.c)));
  const m=[];
  if(r.c&&(dt||r.c)!==r.c)m.push(esc(r.c));
  if(r.loc)m.push(esc(r.loc));
  const d=daysLeft(r.dl);
  if(r.dl){const lab=d==null?"":d<0?"已过":d===0?"今天":"剩"+d+"天";
    m.push('<span class="'+(d!=null&&d>=0&&d<=3?'dl urgent':'dl')+'">截止 '+r.dl+(lab?"("+lab+")":"")+'</span>');}
  if(m.length)c.appendChild(el("div","bm",m.join("<span class=\\"dot\\">·</span>")));
  const nt=noteOf(r.id); if(nt)c.appendChild(el("div","bm","备注："+esc(nt)));
  // 阶段推进：← 上一阶段 / 下一阶段 →
  const idx=STAGES.findIndex(s=>s.k===stg.k);
  const nav=el("div","bnav");
  if(idx>0){const b=el("button",null,"← "+STAGES[idx-1].label);
    b.onclick=()=>{setStatus(r.id,STAGES[idx-1].k);renderTabs();render();};nav.appendChild(b);}
  if(idx<STAGES.length-1){const b=el("button",null,STAGES[idx+1].label+" →");
    b.onclick=()=>{setStatus(r.id,STAGES[idx+1].k);renderTabs();render();};nav.appendChild(b);}
  if(nav.childNodes.length)c.appendChild(nav);
  const row=el("div","bnav");
  if(r.url){const a=el("a","bx","原岗位 ↗");a.href=r.url;a.target="_blank";
    a.style.cssText="flex:1;text-align:center;text-decoration:none";row.appendChild(a);}
  const rm=el("button",null,"移出");rm.onclick=()=>{setStatus(r.id,"");renderTabs();render();};
  row.appendChild(rm);c.appendChild(row);
  return c;
}
function renderBoard(){
  const list=document.getElementById("list");list.innerHTML="";
  const pool=DATA.filter(r=>PIPELINE.has(stOf(r.id))&&secMatch(r));
  document.getElementById("summary").textContent=`投递看板：在投 ${pool.length} 个 · 用 ← / → 推进阶段（忽略不在此显示）`;
  STAGES.forEach(stg=>{
    const col=el("div","bcol");
    const items=pool.filter(r=>stOf(r.id)===stg.k).sort((a,b)=>dlSortKey(a)-dlSortKey(b));
    col.appendChild(el("div","bcolh",stg.label+" <b>"+items.length+"</b>"));
    if(!items.length)col.appendChild(el("div","bempty","—"));
    items.forEach(r=>col.appendChild(boardCard(r,stg)));
    list.appendChild(col);
  });
}
function renderHealth(){
  const list=document.getElementById("list");list.innerHTML="";
  list.classList.remove("board");list.classList.add("health");
  const rows=(HEALTH.sources||[]).slice().sort((a,b)=>{
    const ag=(a.status==="active"&&!a.alert&&!a.err&&!a.skipped)?1:0;
    const bg=(b.status==="active"&&!b.alert&&!b.err&&!b.skipped)?1:0;
    return ag-bg || (b.fails||0)-(a.fails||0) || String(a.id).localeCompare(String(b.id));
  });
  const bad=rows.filter(r=>r.status!=="active"||r.alert||r.err||r.skipped).length;
  document.getElementById("summary").textContent=`信源健康：${rows.length} 个源 · 需关注 ${bad} 个 · 入库 ${HEALTH.store_total||0} · 本次新增 ${HEALTH.new_this_run||0}`;
  let html='<table class="htable"><thead><tr><th>信源</th><th>状态</th><th>数量</th><th>上次成功</th><th>问题</th></tr></thead><tbody>';
  rows.forEach(r=>{
    const good=r.status==="active"&&!r.alert&&!r.err&&!r.skipped;
    const status=good?'<span class="hok">active</span>':'<span class="hbad">'+esc(r.status||"unknown")+'</span>';
    const issue=esc(r.alert||r.err||(r.skipped?"skipped":""));
    html+=`<tr><td><b>${esc(r.id)}</b><br><span class="hmuted">${esc(r.adapter)}</span></td><td>${status}</td><td>${esc(String(r.count||0))}<span class="hmuted"> / peak ${esc(String(r.peak||0))}</span></td><td>${esc(r.ok||"")}</td><td>${issue}</td></tr>`;
  });
  html+='</tbody></table>';
  list.innerHTML=html;
}
renderTabs();
render();
</script></body></html>
"""


def main():
    recs = build_records()
    gen = ""
    try:
        with open(os.path.join(DATA_DIR, "health_report.json"), encoding="utf-8") as f:
            gen = json.load(f).get("generated_at", "")[:16].replace("T", " ")
    except Exception:  # noqa: BLE001
        pass
    out = (_TEMPLATE
           .replace("__DATA__", json.dumps(recs, ensure_ascii=False))
           .replace("__HEALTH__", json.dumps(build_health(), ensure_ascii=False))
           .replace("__BACKLOG__", json.dumps(build_backlog(), ensure_ascii=False))
           .replace("__INBOX__", json.dumps(build_inbox(), ensure_ascii=False))
           .replace("__GEN__", html.escape(gen)))
    path = os.path.join(DATA_DIR, "jobs.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    size = os.path.getsize(path) / 1024
    print(f"✅ 导出 {len(recs)} 条 → {path}  ({size:.0f} KB)")
    print("   双击打开，或： open data/jobs.html")


if __name__ == "__main__":
    main()
