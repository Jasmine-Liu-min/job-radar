#!/usr/bin/env python3
"""兼容入口：快速刷新 27届央国企核心源。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.sync_plan import run_plan  # noqa: E402


def main() -> None:
    run_plan("core")


if __name__ == "__main__":
    main()
