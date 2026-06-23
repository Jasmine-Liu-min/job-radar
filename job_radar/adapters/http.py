"""极简 HTTP 工具（纯标准库，无 requests 依赖）。

所有 adapter 走这里发请求，统一处理：
- 浏览器化默认头（UA / Accept-Language），降低被简单反爬拦截的概率；
- gzip / deflate 自动解压（不少站点无视请求头强制压缩，不解会 JSON 解析失败）；
- 失败重试 + 指数退避（应对偶发抖动）；
- 4xx 客户端错误（401/403/404/412 等）不重试——重试无意义，直接抛给健康度闭环记账。
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
import zlib
from typing import Any, Dict, Optional

DEFAULT_TIMEOUT = 15
MAX_RETRIES = 2          # 总尝试次数 = 1 + MAX_RETRIES
BACKOFF_BASE = 0.8       # 退避基数（秒）：0.8, 1.6, ...

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_BASE_HEADERS = {
    "User-Agent": _UA,
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
}

# 这些状态码重试也没用，直接放弃（交健康度闭环降级）
_NO_RETRY = {400, 401, 403, 404, 405, 412, 451}


def _decompress(raw: bytes, encoding: str) -> bytes:
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def _request(url: str, *, method: str, data: Optional[bytes],
             headers: Dict[str, str], timeout: int) -> bytes:
    last_err: Optional[Exception] = None
    for attempt in range(1 + MAX_RETRIES):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return _decompress(resp.read(), resp.headers.get("Content-Encoding", ""))
        except urllib.error.HTTPError as e:
            if e.code in _NO_RETRY:
                raise
            last_err = e
        except Exception as e:  # noqa: BLE001 — 网络类异常统一重试
            last_err = e
        if attempt < MAX_RETRIES:
            time.sleep(BACKOFF_BASE * (2 ** attempt))
    assert last_err is not None
    raise last_err


def _merge(headers: Optional[Dict[str, str]], extra: Dict[str, str]) -> Dict[str, str]:
    h = dict(_BASE_HEADERS)
    h.update(extra)
    if headers:
        h.update(headers)
    return h


def get_json(url: str, headers: Optional[Dict[str, str]] = None,
             timeout: int = DEFAULT_TIMEOUT) -> Any:
    raw = _request(url, method="GET", data=None,
                   headers=_merge(headers, {"Accept": "application/json, */*"}),
                   timeout=timeout)
    return json.loads(raw)


def post_json(url: str, body: Dict[str, Any],
              headers: Optional[Dict[str, str]] = None,
              timeout: int = DEFAULT_TIMEOUT) -> Any:
    raw = _request(url, method="POST", data=json.dumps(body).encode("utf-8"),
                   headers=_merge(headers, {"Accept": "application/json, */*",
                                            "Content-Type": "application/json"}),
                   timeout=timeout)
    return json.loads(raw)


def post_form(url: str, body: Dict[str, Any],
              headers: Optional[Dict[str, str]] = None,
              timeout: int = DEFAULT_TIMEOUT) -> Any:
    """application/x-www-form-urlencoded 表单 POST，返回 JSON。"""
    import urllib.parse
    raw = _request(url, method="POST", data=urllib.parse.urlencode(body).encode("utf-8"),
                   headers=_merge(headers, {"Accept": "application/json, */*",
                                            "Content-Type": "application/x-www-form-urlencoded"}),
                   timeout=timeout)
    return json.loads(raw)


def get_text(url: str, headers: Optional[Dict[str, str]] = None,
             timeout: int = DEFAULT_TIMEOUT) -> str:
    raw = _request(url, method="GET", data=None,
                   headers=_merge(headers, {}), timeout=timeout)
    return raw.decode("utf-8", errors="replace")
