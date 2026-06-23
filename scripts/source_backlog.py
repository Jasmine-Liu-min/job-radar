#!/usr/bin/env python3
"""查看 27届重点信源 backlog。

运行：
  python3 scripts/source_backlog.py
  python3 scripts/source_backlog.py --status manual_import
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKLOG = ROOT / "config" / "source_backlog.csv"


def main() -> None:
    p = argparse.ArgumentParser(description="查看 27届待接/手动导入信源")
    p.add_argument("--status", help="筛选状态，如 manual_import / blocked / research")
    p.add_argument("--priority", help="筛选优先级，如 1 / 2")
    args = p.parse_args()

    rows = list(csv.DictReader(BACKLOG.read_text(encoding="utf-8").splitlines()))
    if args.status:
        rows = [r for r in rows if r["status"] == args.status]
    if args.priority:
        rows = [r for r in rows if r["priority"] == args.priority]

    for r in rows:
        print(f"[P{r['priority']}] {r['source_id']} · {r['name']} · {r['status']}")
        print(f"  {r['url'] or '(no url)'}")
        print(f"  next: {r['next_action']}")
        if r.get("notes"):
            print(f"  note: {r['notes']}")


if __name__ == "__main__":
    main()
