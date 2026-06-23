#!/usr/bin/env python3
"""兼容入口：快速刷新数据/算法/产品/决策方向的核心官网源。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.sync_plan import run_plan  # noqa: E402


def main() -> None:
    run_plan("role")


if __name__ == "__main__":
    main()
