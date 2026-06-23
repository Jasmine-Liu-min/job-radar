"""Adapter 注册表（registry 模式，参考 viktor-shcherb/job-seek）。

新增一个信源类型 = 写一个返回 List[RawJob] 的函数 + 用 @register("名字") 注册。
config/sources.csv 里的 `adapter` 列即对应这里的名字，sync.py 据此分发。
"""
from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Dict, List

from ..models import RawJob

# adapter 名字 → 抓取函数(endpoint:str) -> List[RawJob]
_REGISTRY: Dict[str, Callable[[str], List[RawJob]]] = {}


def register(name: str):
    """装饰器：把一个抓取函数注册到 registry。"""
    def deco(fn: Callable[[str], List[RawJob]]):
        _REGISTRY[name] = fn
        return fn
    return deco


def get_adapter(name: str) -> Callable[[str], List[RawJob]]:
    if name not in _REGISTRY:
        raise KeyError(f"未注册的 adapter: {name}（已注册: {sorted(_REGISTRY)}）")
    return _REGISTRY[name]


def list_adapters() -> List[str]:
    return sorted(_REGISTRY)


def _auto_import_adapters() -> None:
    """自动导入同目录 adapter 模块以触发 @register 注册。

    新增 adapter 文件后无需再手动维护这里的 import 列表；以下划线开头的工具模块
    （如 _pw.py）会跳过。
    """
    prefix = __name__ + "."
    for mod in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        if mod.name.startswith("_") or mod.name == "__init__":
            continue
        importlib.import_module(prefix + mod.name)


_auto_import_adapters()
