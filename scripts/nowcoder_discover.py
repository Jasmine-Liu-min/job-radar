#!/usr/bin/env python3
"""发现牛客讨论/内推帖链接，写入 data/inbox/nowcoder_urls.txt。

这是低风险版本：不使用账号 cookie，不直接入库，只把候选帖子链接交给
scripts/import_feed.py --preset nowcoder --url-file ... --review-html 审核。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "inbox", "nowcoder_urls.txt")
FEED_OUT = os.path.join(ROOT, "data", "inbox", "nowcoder_discovered.txt")

KEYWORDS = [
    "27届内推", "2027届内推", "2027校招内推", "27届提前批", "27届秋招",
    "提前批内推", "秋招内推", "校招内推", "可转正实习",
    "产品经理校招", "策略产品校招", "AI产品校招",
    "算法校招", "机器学习校招", "数据科学校招", "数据挖掘校招",
]
KEEP = re.compile(
    r"(27届|2027|提前批|秋招|春招|内推|校招|暑期实习|实习|可转正|管培|"
    r"AI|产品|策略|商业分析|数据|算法|机器学习|数据科学|数据挖掘|大模型|推荐)"
)
ACTION = re.compile(
    r"(内推|招聘|招聘信息|校招|秋招|提前批|春招|暑期实习|可转正|岗位|投递|网申|"
    r"开放|补录|直招|hc|HC|实习生招聘|招.*实习|招.*产品|招.*算法|招.*数据)"
)
ROLE_SIGNAL = re.compile(
    r"(产品经理|策略产品|AI产品|算法|机器学习|数据科学|数据挖掘|数据分析|商业分析|大模型|推荐)"
)
NOISE = re.compile(
    r"(简历求|求拷打|求指教|帮.*看看|无实习|0offer|offer比较|offer抉择|怎么选|"
    r"选择|求助|求建议|求帮|帮忙|请问|小白|救救|该接吗|开奖|薪资|面经|一面|二面|三面|笔试|面试|测评|"
    r"复盘|反问|没人权|路线|转.*路线|锐评|投了已读不回|找不到实习|"
    r"找不到|求职进度条|offer帮选|offer对比|offer求对比|实习选offer|选offer|"
    r"项目|上岸|实习意愿|找机会|进面|怎么学|怎么准备|女朋友|"
    r"倾向.*公司|校招or社招|需要.*程度|急急急)"
)
STRONG_ACTION = re.compile(r"(内推码|内推|招聘|招聘信息|正式启动|火热进行|开放|补录|直招|hc|HC|网申|投递)")


def _search_urls(keyword: str, pages: int = 1) -> list[str]:
    q = urllib.parse.quote(keyword)
    urls = []
    for page in range(1, max(1, pages) + 1):
        # Aaronzw/nowcoder_spider 的核心思路：search?type=post&order=time&query=...&page=n
        urls.append(f"https://www.nowcoder.com/search?type=post&order=time&query={q}&page={page}")
        urls.append(f"https://www.nowcoder.com/search?query={q}&type=post&page={page}")
        urls.append(f"https://www.nowcoder.com/discuss?query={q}&page={page}")
    return urls


def _discuss_urls(pages: int = 1) -> list[str]:
    # intzeros/nowcoder_spider 用过 type=2&order=3&page=n；作为全站讨论补充入口。
    return [f"https://www.nowcoder.com/discuss?type=2&order=3&page={p}" for p in range(1, max(1, pages) + 1)]


def discover(keywords: list[str], limit_per_keyword: int = 20, include_discussion: bool = False,
             pages: int = 1, include_discuss_feed: bool = False) -> list[dict]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise SystemExit("未安装 playwright：pip install playwright && python -m playwright install chromium") from e

    found: dict[str, dict] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(15000)
        for kw in keywords:
            urls = _search_urls(kw, pages)
            if include_discuss_feed:
                urls += _discuss_urls(pages)
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(2200)
                try:
                    rows = page.eval_on_selector_all(
                        "a[href*='/discuss/'],a[href*='/feed/main/detail/']",
                        "els=>els.map(e=>({href:e.href,text:(e.innerText||e.textContent||'').trim()}))",
                    )
                except Exception:
                    rows = []
                kept = 0
                for r in rows:
                    href = (r.get("href") or "").split("?")[0]
                    text = _clean_title(r.get("text") or "")
                    if not href or href in found:
                        continue
                    if text and not KEEP.search(text):
                        continue
                    score = _candidate_score(text, kw)
                    if not include_discussion and score < 3:
                        continue
                    if include_discussion and score < 1:
                        continue
                    found[href] = {"url": href, "keyword": kw, "title": text[:120], "quality": score}
                    kept += 1
                    if kept >= limit_per_keyword:
                        break
        browser.close()
    return list(found.values())


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    # 牛客卡片里常混入互动数/作者/摘要，取第一段更适合审核台。
    text = re.split(r"(?:回复|点赞|浏览|收藏|分享|发布于|编辑于)", text)[0].strip()
    return text[:120]


def _candidate_score(text: str, keyword: str) -> int:
    text = text or ""
    score = 0
    if ACTION.search(text):
        score += 3
    if ROLE_SIGNAL.search(text):
        score += 1
    if KEEP.search(text):
        score += 1
    if re.search(r"(27届|2027|提前批|秋招|春招|可转正)", text + keyword):
        score += 1
    if NOISE.search(text):
        score -= 4
    if NOISE.search(text) and not STRONG_ACTION.search(text):
        score -= 3
    if not text or text == "牛客候选招聘帖":
        score -= 1
    return score


def write_urls(rows: list[dict], path: str = OUT, replace: bool = False) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = []
    if os.path.exists(path) and not replace:
        old = [ln.strip() for ln in open(path, encoding="utf-8") if ln.strip() and not ln.startswith("#")]
    seen = set(old)
    new = []
    for r in rows:
        if r["url"] not in seen:
            new.append(r["url"])
            seen.add(r["url"])
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 牛客讨论帖/内推帖 URL，一行一个。由 scripts/nowcoder_discover.py 或人工维护。\n")
        for u in old + new:
            f.write(u + "\n")
    return len(new)


def write_feed(rows: list[dict], path: str = FEED_OUT, replace: bool = False) -> int:
    """把发现结果写成 import_feed 可解析的半结构化文本。

    牛客详情页常被反爬，只有 URL 时无法入审核台；保留标题+链接可先进入人工审核。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = ""
    if os.path.exists(path) and not replace:
        old = open(path, encoding="utf-8", errors="ignore").read()
    seen = set(re.findall(r"https?://\S+", old))
    blocks = []
    for r in rows:
        url = r.get("url", "")
        if not url or url in seen:
            continue
        title = r.get("title") or "牛客候选招聘帖"
        blocks.append(
            "\n".join([
                f"牛客发现：{title}",
                f"链接：{url}",
                f"关键词：{r.get('keyword', '')}",
                f"线索质量：{r.get('quality', '')}",
                "来源：牛客讨论/内推",
                "状态：待人工确认雇主、岗位、截止时间",
            ])
        )
        seen.add(url)
    if not blocks:
        return 0
    with open(path, "w", encoding="utf-8") as f:
        if old.strip():
            f.write(old.rstrip() + "\n\n")
        else:
            f.write("# 牛客发现结果。可用 import_feed --preset nowcoder --text 本文件 --review-html 生成审核台。\n\n")
        f.write("\n\n---\n\n".join(blocks) + "\n")
    return len(blocks)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="发现牛客讨论/内推帖链接，写入 data/inbox/nowcoder_urls.txt。")
    p.add_argument("--keyword", action="append", dest="keywords",
                   help="关键词，可重复；默认覆盖 27届、提前批/秋招/内推、产品/算法/数据方向")
    p.add_argument("--limit-per-keyword", type=int, default=20)
    p.add_argument("--pages", type=int, default=1,
                   help="每个关键词搜索翻页深度；参考公开牛客爬虫的 page 参数，默认 1")
    p.add_argument("--out", default=OUT)
    p.add_argument("--feed-out", default=FEED_OUT,
                   help="额外写出带标题的半结构化文本，供 import_feed --text/--inbox 审核导入")
    p.add_argument("--include-discussion", action="store_true",
                   help="包含简历/面经/路线讨论等弱行动线索；默认只保留更像招聘/内推/投递的帖子")
    p.add_argument("--include-discuss-feed", action="store_true",
                   help="额外扫描 discuss?type=2&order=3&page=n 全站讨论流，噪声更高")
    p.add_argument("--replace", action="store_true",
                   help="覆盖输出文件，而不是追加；适合每天生成干净待审核池")
    args = p.parse_args(argv)
    rows = discover(args.keywords or KEYWORDS, args.limit_per_keyword, args.include_discussion,
                    args.pages, args.include_discuss_feed)
    added = write_urls(rows, args.out, args.replace)
    feed_added = write_feed(rows, args.feed_out, args.replace)
    print(f"发现 {len(rows)} 个候选链接，新增 URL {added} 个 → {args.out}")
    print(f"新增可审核标题块 {feed_added} 个 → {args.feed_out}")
    print(f"下一步：python3 scripts/import_feed.py --preset nowcoder --text {args.feed_out} --review-html")


if __name__ == "__main__":
    main(sys.argv[1:])
