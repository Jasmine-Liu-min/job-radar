"""共享的 Playwright 浏览器单实例。

多个 SPA adapter（uni_spa 的复旦/南大、sjtu 的上交）原本各自 launch 一个无头浏览器，
启动开销叠加。这里改为全进程共用一个浏览器：首次 new_page() 惰性启动，sync 结束调
shutdown() 释放。

可选依赖：未安装 playwright 时 new_page() 抛清晰的 RuntimeError，由健康度闭环记账降级。
"""
from __future__ import annotations

_pw = None
_browser = None


def _ensure():
    global _pw, _browser
    if _browser is None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "未安装 playwright；请运行 "
                "`pip install playwright && python -m playwright install chromium`"
            ) from e
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(headless=True)
    return _browser


def new_page():
    """返回共享浏览器的一个新 page；用完请 page.close()。"""
    return _ensure().new_page()


def shutdown() -> None:
    """关闭共享浏览器（sync 结束时调用）；未启动则无操作。"""
    global _pw, _browser
    if _browser is not None:
        try:
            _browser.close()
        except Exception:  # noqa: BLE001
            pass
        _browser = None
    if _pw is not None:
        try:
            _pw.stop()
        except Exception:  # noqa: BLE001
            pass
        _pw = None
