#!/usr/bin/env python3
"""发送 Job Radar 新增推送。

默认只发送 notify_preview 选出的"未推新增"；发送成功后才写 notify_state.json。
没有 webhook 环境变量时安全跳过，方便先接进 GitHub Actions。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

import notify_preview


def webhook_from_env() -> tuple[str, str]:
    feishu = os.getenv("FEISHU_WEBHOOK_URL", "").strip()
    wechat = os.getenv("WECHAT_WEBHOOK_URL", "").strip() or os.getenv("WECOM_WEBHOOK_URL", "").strip()
    if feishu:
        return "feishu", feishu
    if wechat:
        return "wecom", wechat
    return "", ""


def post_json(url: str, payload: dict, timeout: int = 15) -> tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return e.code, body


def feishu_post_payload(text: str) -> dict:
    lines = text.splitlines()
    title = (lines[0].lstrip("#").strip() if lines else "Job Radar") or "Job Radar"
    content = []
    for raw in lines[1:]:
        line = raw.strip()
        if not line:
            content.append([{"tag": "text", "text": "\n"}])
            continue
        if line.startswith("## "):
            content.append([{"tag": "text", "text": line[3:].strip()}])
            continue
        if line.startswith("http://") or line.startswith("https://"):
            content.append([{"tag": "a", "text": "查看链接", "href": line}])
            continue
        if "：" in line and "https://" in line:
            label, href = line.split("：", 1)
            content.append([
                {"tag": "text", "text": f"{label}："},
                {"tag": "a", "text": href, "href": href},
            ])
            continue
        content.append([{"tag": "text", "text": line}])
    return {"msg_type": "post", "content": {"post": {"zh_cn": {"title": title, "content": content}}}}


def payload_for(channel: str, text: str) -> dict:
    if channel == "wecom":
        return {"msgtype": "markdown", "markdown": {"content": text}}
    return feishu_post_payload(text)


def main() -> None:
    p = argparse.ArgumentParser(description="发送 Job Radar 未推新增摘要。")
    p.add_argument("--out", default=notify_preview.OUT)
    p.add_argument("--state", default=notify_preview.STATE)
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--min-focus", type=int, default=120)
    p.add_argument("--min-match", type=int, default=50)
    p.add_argument("--since", default="")
    p.add_argument("--include-existing-due", action="store_true")
    p.add_argument("--channel", choices=("auto", "feishu", "wecom"), default="auto")
    p.add_argument("--webhook", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-mark", action="store_true", help="发送成功后不写 notify_state.json")
    p.add_argument("--workbench-url", default=os.getenv("WORKBENCH_URL", "").strip(),
                   help="推送中展示的在线工作台链接")
    args = p.parse_args()

    md, selected = notify_preview.build(
        limit=args.limit,
        min_focus=args.min_focus,
        min_match=args.min_match,
        mode="new",
        since=args.since,
        include_existing_due=args.include_existing_due,
        state_path=args.state,
        workbench_url=args.workbench_url,
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)

    if not selected:
        print("无未推新增重点岗位，跳过发送。")
        return

    channel, webhook = (args.channel, args.webhook.strip()) if args.webhook else webhook_from_env()
    if args.channel != "auto":
        channel = args.channel
    if args.dry_run or not webhook:
        print(f"生成预览但未发送：{args.out}（未配置 webhook 或 dry-run）。")
        print(f"本次待推 {len(selected)} 条；不会写 {args.state}。")
        return

    status, body = post_json(webhook, payload_for(channel or "feishu", md))
    if status < 200 or status >= 300:
        print(f"推送失败：HTTP {status} {body}", file=sys.stderr)
        sys.exit(1)

    print(f"推送成功：HTTP {status}")
    if not args.no_mark:
        added = notify_preview.mark_pushed(args.state, selected)
        print(f"已标记 {added} 条为已推送：{args.state}")


if __name__ == "__main__":
    main()
