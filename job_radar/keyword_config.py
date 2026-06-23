"""补抓关键词配置。

关键词型招聘接口（如字节、腾讯、京东、国聘）默认排序可能漏掉目标方向。
这里从 config/role_keywords.json 读取统一关键词，避免每个 adapter 各写一份。
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Iterable, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config", "role_keywords.json")

_DEFAULTS = {
    "intern": ["实习"],
    "data_algo": ["算法", "机器学习", "数据科学", "数据挖掘", "推荐算法", "大模型"],
    "product": ["AI产品", "策略产品", "数据产品"],
    "decision": ["战略分析", "经营分析", "商业分析", "行业研究", "管培生", "数字化转型"],
    "campus_cycle": ["2027", "27届", "提前批", "央企校招", "国企校招", "秋招", "春招"],
    "iguopin_extra": ["大模型算法"],
}


@lru_cache(maxsize=1)
def load_keywords() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        data = {}
    out = dict(_DEFAULTS)
    for k, v in data.items():
        if isinstance(v, list):
            out[k] = [str(x).strip() for x in v if str(x).strip()]
    return out


def keywords(*groups: str) -> List[str]:
    cfg = load_keywords()
    out: List[str] = []
    for g in groups:
        vals: Iterable[str] = cfg.get(g, [])
        for v in vals:
            if v and v not in out:
                out.append(v)
    return out


def role_focus_keywords() -> List[str]:
    return keywords("intern", "data_algo")


def iguopin_keywords() -> List[str]:
    return keywords("campus_cycle", "product", "decision", "data_algo", "iguopin_extra")
