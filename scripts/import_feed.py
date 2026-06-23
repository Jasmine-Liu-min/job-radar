#!/usr/bin/env python3
"""把"学校就业群推送"导入工作台（腾讯文档表格汇总 / 公众号推文 / 群消息文本）。

群里那种推送之所以全，是人工众包 + 企业直投学校——抓不到闭群，但你能把内容喂进来。
本工具用**纯规则**（不依赖 AI）把这些半结构化内容抽成岗位，并入 data/jobs.json：

用法：
  # 1) 腾讯文档/在线表格：先在腾讯文档「导出为 CSV」，再：
  python3 scripts/import_feed.py 汇总表.csv

  # 2) 公众号推文：直接喂文章链接（mp.weixin.qq.com/s/...，可多个）
  python3 scripts/import_feed.py --url https://mp.weixin.qq.com/s/xxxx

  # 3) 群消息文本：把群里复制的一大段存成 txt
  python3 scripts/import_feed.py --text 群消息.txt

  # 4) 标记来源（推荐）：让牛客帖/公众号/学校群在工作台里可追踪
  python3 scripts/import_feed.py --source-id feed-nowcoder --source-name 牛客内推帖 --url https://www.nowcoder.com/discuss/xxxx

导入后自动重出 data/jobs.html。默认导入源 source_id=feed-import，类别"群推送"，
可信度按 aggregator(50)——未经核验，分数不会盖过官方源；解析不准的可在工作台忽略。
"""
from __future__ import annotations

import argparse
import csv
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from job_radar import sync                       # noqa: E402
from job_radar.adapters.http import get_text     # noqa: E402
from job_radar.dedup import dedup                 # noqa: E402
from job_radar.models import RawJob               # noqa: E402
from job_radar.quality_rules import quality_tags   # noqa: E402
from job_radar.score import score_job             # noqa: E402
import json                                        # noqa: E402

PRESETS = {
    "nowcoder": ("feed-nowcoder", "牛客内推帖"),
    "wechat": ("feed-wechat", "公众号招聘"),
    "group": ("feed-school-group", "学校群汇总"),
    "campus": ("feed-campus-office", "就业办/学院通知"),
}


def _src(source_id: str, source_name: str) -> dict:
    """导入源的合成 src（_to_jobs 需要这些键）。"""
    return {"source_id": source_id, "company_name": source_name,
            "org_type": "", "source_type": "aggregator", "adapter": "import"}

_URL_RE = re.compile(r"https?://[^\s一-鿿，。、；）)】」'\"]+")
_DATE_RE = re.compile(r"(20\d{2}[./年-]\d{1,2}[./月-]\d{1,2}|\d{1,2}\s*[./月-]\s*\d{1,2}日?)")
_DDL_RE = re.compile(r"(截止|deadline|ddl|投递截止|报名截止)[:：\s]*" + _DATE_RE.pattern, re.I)
_ORG_RE = re.compile(r"(公司|集团|股份|有限|科技|银行|研究院|研究所|大学|学院|医院|"
                     r"事业|中心|实验室|局|厂|控股|证券|基金|保险|电力|能源|汽车|半导体|"
                     r"生物|制药|医药|通信|网络|数据|智能|事业群|部门)")
_KNOWN_EMPLOYERS = [
    "科大讯飞", "禾赛科技", "基恩士", "米哈游", "图拉斯", "腾讯", "途游游戏",
    "韶音科技", "拼多多", "PDD", "OPPO", "游卡", "蔚来", "南京银行", "荣耀",
    "极兔速递", "快手", "小鹏汽车", "百度", "美团", "淘宝", "字节", "京东",
    "网易", "华为", "海信集团", "超星集团", "万兴科技", "神州数码", "同花顺",
    "知乎", "中通", "阿里", "蚂蚁", "滴滴", "小米", "B站", "哔哩哔哩",
]
# 列名模糊匹配（腾讯文档汇总表常见表头）
_COLS = {
    "company": ["公司", "单位", "企业", "名称", "company", "招聘单位"],
    "title":   ["岗位", "职位", "position", "job", "招聘岗位", "方向"],
    "url":     ["链接", "网申", "投递", "网址", "link", "url", "内推", "报名", "申请"],
    "deadline": ["截止", "ddl", "deadline", "投递截止"],
    "location": ["地点", "城市", "工作地", "base", "location", "地区"],
    "publish": ["发布", "时间", "date", "更新"],
    "jtype":   ["类型", "性质", "类别"],
}


def _norm_date(s: str) -> str:
    s = (s or "").strip().replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
    m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def _infer_company(text: str) -> str:
    """从牛客/群推送标题里猜雇主名；只做保守候选，审核台仍可改。"""
    compact = re.sub(r"\s+", " ", text or "").strip(" ：:【】[]#")
    compact = re.sub(r"^牛客发现[:：]\s*", "", compact)
    for name in _KNOWN_EMPLOYERS:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", compact, re.I):
            return name
    m = re.match(
        r"([A-Za-z0-9一-鿿·]{2,16}?)(?:202[67]届|27届|26届|校招|秋招|春招|提前批|暑期实习|"
        r"实习生|内推|招聘|直招|补录|管培|产品经理|算法|数据|AI)",
        compact,
        re.I,
    )
    if m:
        cand = m.group(1).strip(" -—·:：,，")
        if cand and not re.search(r"(本人|现在|这周|关于|求|想|校招|春招|秋招|产品经理|算法|数据|大模型|github)", cand, re.I):
            return cand[:20]
    return ""


def _map_cols(header: list) -> dict:
    """表头 → 字段名 的模糊映射。"""
    out = {}
    for i, h in enumerate(header):
        hl = (h or "").strip().lower()
        for field, kws in _COLS.items():
            if field in out:
                continue
            if any(k.lower() in hl for k in kws):
                out[field] = i
                break
    return out


def from_table(path: str) -> list:
    """读 CSV/TSV（腾讯文档导出），按列映射成 RawJob。"""
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", "ignore")
    delim = "\t" if text[:2000].count("\t") > text[:2000].count(",") else ","
    rows = list(csv.reader(text.splitlines(), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return []
    # 找表头行：含"公司/岗位/链接"任一关键字的第一行
    hi = 0
    for i, r in enumerate(rows[:8]):
        joined = " ".join(r).lower()
        if any(k in joined for k in ("公司", "岗位", "职位", "单位", "链接", "投递")):
            hi = i
            break
    cmap = _map_cols(rows[hi])
    jobs = []
    for r in rows[hi + 1:]:
        def cell(f):
            i = cmap.get(f)
            return (r[i].strip() if i is not None and i < len(r) else "")
        company, title = cell("company"), cell("title")
        url = cell("url")
        if not url:  # 链接可能混在任意单元格
            for c in r:
                m = _URL_RE.search(c)
                if m:
                    url = m.group(0)
                    break
        if not (company or title):
            continue
        jtype = cell("jtype")
        title2 = title or company
        if jtype and jtype not in title2:
            title2 = f"{title2}（{jtype}）"
        jobs.append(RawJob(
            company_name=company, title=title2, location=cell("location"),
            publish_time=_norm_date(cell("publish")), deadline=_norm_date(cell("deadline")),
            official_url=url, jd_text=" ".join(filter(None, r))[:600],
            raw={"platform": "feed", "via": "表格汇总"}))
    return jobs


def from_text(text: str, via: str = "群消息") -> list:
    """从自由文本/文章正文按"块"启发式抽岗位：以含链接或公司词的行为锚。"""
    text = re.sub(r"(?m)^\s*(?:\d{1,3}[.)、]|[-*•●])\s+", "\n\n", text)
    text = re.sub(r"(https?://)", r"\n\1", text)
    blocks = re.split(r"\n{2,}|\r\n\r\n", text)
    if len(blocks) < 3:  # 没有空行分块就按行
        blocks = text.splitlines()
    jobs, seen = [], set()
    for b in blocks:
        b = b.strip()
        if len(b) < 6:
            continue
        url_m = _URL_RE.search(b)
        has_org = _ORG_RE.search(b)
        if not (url_m or has_org):
            continue
        url = url_m.group(0) if url_m else ""
        # 公司：取含机构词、最短的一段；标题：块首行
        first = b.splitlines()[0].strip(" -—·:：【】[]")
        comp_m = re.search(r"[一-鿿（）()A-Za-z0-9·]{2,34}?(公司|集团|股份|银行|研究院|研究所|大学|学院|科技|医院|证券|基金|保险|事业群|部门|中心|局|厂)", b)
        company = comp_m.group(0) if comp_m else _infer_company(first)
        ddl = ""
        dm = _DDL_RE.search(b) or _DATE_RE.search(b)
        if dm:
            ddl = _norm_date(dm.group(0))
        title = first[:60] or company
        key = (company, title, url)
        if key in seen:
            continue
        seen.add(key)
        jobs.append(RawJob(
            company_name=company, title=title, location="",
            deadline=ddl, official_url=url, jd_text=b[:600],
            raw={"platform": "feed", "via": via, "needs_review": True}))
    return jobs


def from_url(url: str) -> list:
    """抓公众号/网页文章正文 → from_text。微信正文在 #js_content 内。"""
    html = get_text(url)
    m = re.search(r'id="js_content"[^>]*>(.*?)</div>\s*<', html, re.S) or \
        re.search(r'<article[^>]*>(.*?)</article>', html, re.S)
    body = m.group(1) if m else html
    body = re.sub(r"<br\s*/?>", "\n", body)
    body = re.sub(r"</(p|div|li|tr|h\d)>", "\n", body)
    text = re.sub(r"<[^>]+>", "", body)
    text = re.sub(r"&nbsp;|&amp;", " ", text)
    via = "公众号推文" if "weixin" in url else "网页文章"
    return from_text(text, via=via)


def urls_from_file(path: str) -> list:
    text = open(path, encoding="utf-8", errors="ignore").read()
    return list(dict.fromkeys(_URL_RE.findall(text)))


def from_url_file(path: str) -> list:
    """URL 文件导入：先抓详情；失败时用文件里的标题/链接块兜底进审核台。"""
    raws = []
    text = open(path, encoding="utf-8", errors="ignore").read()
    informative_text = re.sub(_URL_RE, "", text)
    informative_text = re.sub(r"(?m)^\s*#.*$", "", informative_text).strip()
    failed = 0
    for u in list(dict.fromkeys(_URL_RE.findall(text))):
        try:
            got = from_url(u)
            print(f"  {u[:50]}… 抽出 {len(got)} 条")
            raws += got
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  抓取失败 {u[:50]}…: {type(e).__name__}: {e}")
    fallback = from_text(text, via=f"url-file:{os.path.basename(path)}") if ((failed or not raws) and informative_text) else []
    if fallback:
        known = {(r.official_url, r.title) for r in raws}
        added = 0
        for r in fallback:
            key = (r.official_url, r.title)
            if key in known:
                continue
            raws.append(r)
            known.add(key)
            added += 1
        if failed:
            print(f"  URL 详情失败 {failed} 个，已用文件文本兜底补 {added} 条待审核候选")
    return raws


def from_inbox(path: str) -> list:
    """扫描目录：*.csv/*.tsv 走表格，*.txt/*.md 走文本并抽 URL，*.url/urls.txt 走 URL。"""
    raws = []
    if not os.path.isdir(path):
        raise SystemExit(f"--inbox 需要目录：{path}")
    for name in sorted(os.listdir(path)):
        p = os.path.join(path, name)
        if os.path.isdir(p) or name.startswith("."):
            continue
        low = name.lower()
        try:
            if low.endswith((".csv", ".tsv")):
                got = from_table(p)
                print(f"  表格 {name}: {len(got)} 条")
                raws += got
            elif low.endswith((".txt", ".md")):
                text = open(p, encoding="utf-8", errors="ignore").read()
                if urls_from_file(p):
                    got = from_url_file(p)
                else:
                    got = from_text(text, via=f"inbox:{name}")
                print(f"  文本 {name}: {len(got)} 条")
                raws += got
            elif low.endswith((".url", ".urls")):
                for u in urls_from_file(p):
                    try:
                        got = from_url(u)
                        print(f"  URL {u[:50]}…: {len(got)} 条")
                        raws += got
                    except Exception as e:  # noqa: BLE001
                        print(f"  URL 抓取失败 {u[:50]}…: {type(e).__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  跳过 {name}: {type(e).__name__}: {e}")
    return raws


def merge(raws: list, src: dict) -> tuple:
    """打分 + 加性并入 data/jobs.json（不动其它源），返回 (新增, 刷新, 总量)。"""
    jobs = dedup(sync._to_jobs(src, raws))
    profiles = json.load(open(sync.PROFILES_JSON, encoding="utf-8"))
    for j in jobs:
        best = max((score_job(j, p) for p in profiles.values()), key=lambda r: r.score)
        qtags, qrisks = quality_tags(j)
        j.match_score = best.score
        j.tags = list(dict.fromkeys(([f"行业:{j.industry}"] if j.industry else []) + best.tags + qtags))
        j.risk_flags = list(dict.fromkeys(j.risk_flags + best.risk_flags + qrisks))
    now = sync._now()
    path = os.path.join(sync.DATA_DIR, "jobs.json")
    by_key = {r.get("dedup_key"): r for r in json.load(open(path, encoding="utf-8")) if r.get("dedup_key")}
    add = ref = 0
    for j in jobs:
        d = j.to_dict()
        k = d.get("dedup_key")
        if not k:
            continue
        o = by_key.get(k)
        if o:
            d["first_seen"] = o.get("first_seen") or now
            d["status"] = o.get("status") or "new"
            ref += 1
        else:
            d["first_seen"] = now
            d["status"] = "new"
            add += 1
        d["last_seen"] = now
        d["gone"] = False
        by_key[k] = d
    merged = sorted(by_key.values(), key=lambda d: d.get("match_score", 0), reverse=True)
    json.dump(merged, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return add, ref, len(merged)


def score_raws(raws: list, src: dict):
    jobs = dedup(sync._to_jobs(src, raws))
    profiles = json.load(open(sync.PROFILES_JSON, encoding="utf-8"))
    for j in jobs:
        best = max((score_job(j, p) for p in profiles.values()), key=lambda r: r.score)
        qtags, qrisks = quality_tags(j)
        j.match_score = best.score
        j.tags = list(dict.fromkeys(([f"行业:{j.industry}"] if j.industry else []) + best.tags + qtags))
        j.risk_flags = list(dict.fromkeys(j.risk_flags + best.risk_flags + qrisks))
    return sorted(jobs, key=lambda j: j.match_score, reverse=True)


def _job_to_raw(j: RawJob | dict) -> RawJob:
    if isinstance(j, RawJob):
        return j
    return RawJob(
        company_name=str(j.get("company_name", "")).strip(),
        title=str(j.get("title", "")).strip(),
        location=str(j.get("location", "")).strip(),
        publish_time=str(j.get("publish_time", "")).strip(),
        deadline=str(j.get("deadline", "")).strip(),
        official_url=str(j.get("official_url", "")).strip(),
        jd_text=str(j.get("jd_text", "")).strip(),
        raw=dict(j.get("raw") or {}),
    )


def export_review_html(raws: list, src: dict, path: str) -> str:
    """生成可人工审核的 HTML：勾选/改字段后导出 JSON，再用 --review-json 导入。"""
    jobs = score_raws(raws, src)
    rows = []
    for j in jobs:
        rows.append({
            "company_name": j.company_name,
            "title": j.title,
            "location": j.location,
            "publish_time": j.publish_time,
            "deadline": j.deadline,
            "official_url": j.official_url,
            "jd_text": j.jd_text,
            "raw": j.extra if hasattr(j, "extra") else {},
            "score": j.match_score,
            "tags": j.tags,
            "risk_flags": j.risk_flags,
        })
    tpl = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>导入审核台</title>
<style>
:root{--ink:#30343b;--muted:#777f8b;--bd:#e5e8ee;--fog:#f5f7fa;--ok:#4f7d63;--warn:#a56662}
*{box-sizing:border-box}body{margin:0;background:#fbfcfd;color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.92);backdrop-filter:blur(10px);border-bottom:1px solid var(--bd);padding:16px 22px}
h1{margin:0 0 8px;font-size:22px;font-weight:600}.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.stat{color:var(--muted);font-size:12px}
input,select,textarea{font:inherit;border:1px solid var(--bd);border-radius:8px;background:#fff;color:var(--ink);padding:7px 9px}
button{cursor:pointer;border:1px solid var(--bd);border-radius:999px;background:#fff;color:var(--ink);padding:7px 12px}
button.primary{background:var(--ink);color:#fff;border-color:var(--ink)}button:hover{border-color:var(--ink)}
main{max-width:1260px;margin:0 auto;padding:18px 22px;display:grid;gap:12px}
.row{display:grid;grid-template-columns:32px 74px 1fr 1fr 120px 110px 120px;gap:8px;align-items:start;background:#fff;border:1px solid var(--bd);border-radius:12px;padding:10px;box-shadow:0 10px 24px -18px rgba(20,25,35,.25)}
.row.drop{opacity:.45}.score{font-weight:600;color:var(--ok)}.risk .score{color:var(--warn)}
.cell label{display:block;color:var(--muted);font-size:11px;margin-bottom:3px}.cell input,.cell textarea{width:100%}.jd{grid-column:3/-1}.jd textarea{min-height:54px;resize:vertical}.tags{color:var(--muted);font-size:12px;word-break:break-all}
.pill{display:inline-block;border-radius:999px;background:var(--fog);padding:2px 7px;margin:0 3px 3px 0}.pill.r{color:var(--warn)}
@media(max-width:900px){.row{grid-template-columns:28px 56px 1fr}.cell,.jd{grid-column:auto}.jd{grid-column:1/-1}}
</style></head><body><header>
<h1>导入审核台 <span class="stat" id="sum"></span></h1>
<div class="bar">
  <input id="q" placeholder="搜索公司 / 岗位 / 标签" style="min-width:260px;flex:1">
  <select id="risk"><option value="all">全部</option><option value="clean">仅低风险</option><option value="risk">仅风险项</option><option value="missing">缺字段</option></select>
  <button id="all">全选</button><button id="none">全不选</button>
  <button class="primary" id="dl">导出审核 JSON</button>
</div>
<div class="stat">修改字段和勾选状态后，点击“导出审核 JSON”，再运行：python3 scripts/import_feed.py --review-json 下载文件.json</div>
</header><main id="list"></main>
<script>
let DATA=__DATA__;
function esc(s){return (s||"").replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]));}
function bad(r){return !r.company_name||!r.title||!r.official_url||!r.deadline||(r.tags||[]).some(t=>["代招/委托","猎头","劳务派遣","泛销售","低相关管培","地点风险","缺官网链接"].includes(t));}
function readRow(el,r){["company_name","title","location","deadline","official_url","jd_text"].forEach(k=>{const x=el.querySelector(`[data-k="${k}"]`);if(x)r[k]=x.value.trim();});r.keep=el.querySelector('[data-k="keep"]').checked;}
function filtered(){const q=document.getElementById("q").value.trim().toLowerCase();const f=document.getElementById("risk").value;
 return DATA.filter(r=>{const b=bad(r);if(f==="clean"&&b)return false;if(f==="risk"&&!b)return false;if(f==="missing"&&!(!r.company_name||!r.title||!r.official_url||!r.deadline))return false;
 const hay=(r.company_name+" "+r.title+" "+(r.tags||[]).join(" ")+" "+r.jd_text).toLowerCase();return !q||hay.includes(q);});}
function render(){const list=document.getElementById("list");list.innerHTML="";const rows=filtered();
 document.getElementById("sum").textContent=`· ${DATA.filter(r=>r.keep!==false).length}/${DATA.length} 待导入 · 当前 ${rows.length}`;
 rows.forEach((r,i)=>{const idx=DATA.indexOf(r);const div=document.createElement("section");div.className="row"+(r.keep===false?" drop":"")+(bad(r)?" risk":"");div.dataset.idx=idx;
 div.innerHTML=`<input data-k="keep" type="checkbox" ${r.keep===false?"":"checked"}><div class="score">${r.score||0}</div>
 <div class="cell"><label>公司</label><input data-k="company_name" value="${esc(r.company_name)}"></div>
 <div class="cell"><label>岗位</label><input data-k="title" value="${esc(r.title)}"></div>
 <div class="cell"><label>城市</label><input data-k="location" value="${esc(r.location)}"></div>
 <div class="cell"><label>截止</label><input data-k="deadline" value="${esc(r.deadline)}"></div>
 <div class="cell"><label>链接</label><input data-k="official_url" value="${esc(r.official_url)}"></div>
 <div class="tags">${(r.tags||[]).slice(0,10).map(t=>`<span class="pill ${bad(r)&&["代招/委托","猎头","劳务派遣","泛销售","低相关管培","地点风险","缺官网链接"].includes(t)?"r":""}">${esc(t)}</span>`).join("")}</div>
 <div class="jd"><label class="stat">原文 / JD</label><textarea data-k="jd_text">${esc(r.jd_text)}</textarea></div>`;
 div.addEventListener("input",()=>{readRow(div,r);div.classList.toggle("drop",r.keep===false);div.classList.toggle("risk",bad(r));document.getElementById("sum").textContent=`· ${DATA.filter(x=>x.keep!==false).length}/${DATA.length} 待导入 · 当前 ${rows.length}`;});
 list.appendChild(div);});}
document.getElementById("q").oninput=render;document.getElementById("risk").onchange=render;
document.getElementById("all").onclick=()=>{DATA.forEach(r=>r.keep=true);render();};
document.getElementById("none").onclick=()=>{DATA.forEach(r=>r.keep=false);render();};
document.getElementById("dl").onclick=()=>{const kept=DATA.filter(r=>r.keep!==false).map(({score,tags,risk_flags,keep,...r})=>r);
 const blob=new Blob([JSON.stringify({source:__SRC__,jobs:kept},null,2)],{type:"application/json"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="job_import_review.json";a.click();};
DATA.forEach(r=>{if(r.keep==null)r.keep=!bad(r);});render();
</script></body></html>"""
    out = (tpl
           .replace("__DATA__", json.dumps(rows, ensure_ascii=False))
           .replace("__SRC__", json.dumps(src, ensure_ascii=False)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path


def from_review_json(path: str) -> tuple[list, dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    src = data.get("source") or _src("feed-import", "群推送导入")
    raws = [_job_to_raw(r) for r in data.get("jobs", []) if r.get("company_name") or r.get("title")]
    return raws, src


def preview(raws: list, src: dict, limit: int = 20) -> None:
    jobs = score_raws(raws, src)
    no_company = sum(not j.company_name for j in jobs)
    no_url = sum(not j.official_url for j in jobs)
    no_deadline = sum(not j.deadline for j in jobs)
    qtags = ("代招/委托", "猎头", "劳务派遣", "泛销售", "低相关管培", "地点风险", "缺官网链接")
    risky = sum(bool(set(j.tags) & set(qtags)) for j in jobs)
    print(f"\n预览：抽出 {len(raws)} 条 → 去重后 {len(jobs)} 条")
    print(f"缺公司 {no_company} / 缺链接 {no_url} / 缺截止 {no_deadline} / 质量风险 {risky}")
    print("\nTop 样本：")
    for j in jobs[:limit]:
        tags = " ".join(t for t in j.tags if not t.startswith("行业:"))[:80]
        url = "有链接" if j.official_url else "缺链接"
        ddl = j.deadline or "缺截止"
        print(f"- {j.match_score:>3} {j.company_name or '未知公司'}｜{j.title}｜{ddl}｜{url}｜{tags}")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="导入 27届校招/实习半结构化信源（腾讯文档、公众号、牛客帖、群消息）。")
    p.add_argument("table", nargs="?", help="腾讯文档/表格导出的 CSV/TSV")
    p.add_argument("--url", nargs="+", help="公众号/网页/牛客帖子 URL，可多个")
    p.add_argument("--url-file", help="包含多个牛客/公众号/网页链接的 txt/md 文件")
    p.add_argument("--text", help="群消息文本文件")
    p.add_argument("--inbox", help="批量导入目录：可放 CSV/TSV、群消息 txt/md、URL 列表")
    p.add_argument("--preset", choices=sorted(PRESETS),
                   help="快速设置来源：nowcoder/wechat/group/campus")
    p.add_argument("--source-id", default="feed-import",
                   help="导入源 id，例如 feed-nowcoder / feed-wechat / feed-school-group")
    p.add_argument("--source-name", default="群推送导入",
                   help="导入源名称，会作为未识别公司名时的兜底名称")
    p.add_argument("--preview", action="store_true",
                   help="只预览解析和打分结果，不写入 data/jobs.json")
    p.add_argument("--preview-limit", type=int, default=20,
                   help="预览展示的样本数")
    p.add_argument("--review-html", nargs="?", const=os.path.join(sync.DATA_DIR, "import_preview.html"),
                   help="生成可人工勾选/编辑的 HTML 审核台，不写入 jobs.json")
    p.add_argument("--review-json",
                   help="导入审核台导出的 JSON，只写入保留项")
    return p


def main(argv: list) -> None:
    if not argv:
        print(__doc__)
        return
    args = _parser().parse_args(argv)
    raws = []
    if args.preset:
        args.source_id, args.source_name = PRESETS[args.preset]
    src = _src(args.source_id, args.source_name)
    if args.review_json:
        raws, src = from_review_json(args.review_json)
    elif args.inbox:
        raws = from_inbox(args.inbox)
    elif args.url:
        for u in args.url:
            try:
                got = from_url(u)
                print(f"  {u[:50]}… 抽出 {len(got)} 条")
                raws += got
            except Exception as e:  # noqa: BLE001
                print(f"  抓取失败 {u[:50]}…: {type(e).__name__}: {e}")
    elif args.url_file:
        raws = from_url_file(args.url_file)
    elif args.text:
        raws = from_text(open(args.text, encoding="utf-8", errors="ignore").read())
    elif args.table:
        raws = from_table(args.table)
    else:
        print(__doc__)
        return
    raws = [r for r in raws if (r.company_name or r.title)]
    if not raws:
        print("没抽到岗位。表格请确认有 公司/岗位/链接 列；文章可能被反爬或正文为空。")
        return
    if args.review_html:
        path = export_review_html(raws, src, args.review_html)
        print(f"审核台已生成：{path}")
        print(f"审核后导入：python3 scripts/import_feed.py --review-json 下载的JSON文件")
        return
    if args.preview:
        preview(raws, src, args.preview_limit)
        return
    add, ref, total = merge(raws, src)
    print(f"\n抽出 {len(raws)} 条 → 新增 {add} / 刷新 {ref}，库总量 {total}")
    from scripts import export_html  # noqa: E402
    export_html.main()


if __name__ == "__main__":
    main(sys.argv[1:])
