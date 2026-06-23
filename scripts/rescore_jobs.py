#!/usr/bin/env python3
"""兼容入口：按最新画像重新计算 data/jobs.json 的匹配分与标签。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.sync_plan import run_plan  # noqa: E402


def main() -> None:
    run_plan("rescore")


if __name__ == "__main__":
    main()
