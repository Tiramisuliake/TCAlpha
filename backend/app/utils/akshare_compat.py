"""AKShare 兼容补丁：注入默认 User-Agent。

AKShare 1.18.x 内部 ``requests.get`` 不带 headers，会被部分 eastmoney 接口
（push2his / 实时分钟 K）以 403/RemoteDisconnected 拒绝。本模块在首次调用
``patch_requests_ua()`` 时打补丁到 ``requests.api.request``，让所有未显式
传 headers 的请求自动带上浏览器 UA。

只需 import 即可自动激活：

    from app.utils import akshare_compat  # noqa: F401
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_patched = False
_eastmoney_session: requests.Session | None = None


def _get_eastmoney_session() -> requests.Session:
    """长寿命 Session：复用 TCP keep-alive + 自动重试连接/5xx 错误。

    分页快照（stock_zh_a_spot_em 58 页）在 eastmoney 子域名上易触发
    RemoteDisconnected，Retry 会在 backoff 后自动重试。
    """
    global _eastmoney_session
    if _eastmoney_session is None:
        s = requests.Session()
        s.trust_env = False  # 绕开 Windows 注册表 / .netrc 自动代理
        s.headers.update({
            "User-Agent": _DEFAULT_UA,
            "Referer": "https://quote.eastmoney.com/",
            "Accept": "*/*",
        })
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.5,            # 0.5, 1, 2, 4 s
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            pool_connections=20, pool_maxsize=20, max_retries=retry,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _eastmoney_session = s
    return _eastmoney_session


def patch_requests_ua() -> None:
    global _patched
    if _patched:
        return
    orig_request = requests.api.request

    def request_with_ua(method, url, **kwargs):
        headers = kwargs.pop("headers", None) or {}
        if "eastmoney.com" in url:
            # 用长寿命 Session 维持 TCP keep-alive（默认 headers 已含 UA + Referer）
            return _get_eastmoney_session().request(
                method=method, url=url, headers=headers, **kwargs
            )
        if not any(k.lower() == "user-agent" for k in headers):
            headers["User-Agent"] = _DEFAULT_UA
        return orig_request(method, url, headers=headers, **kwargs)

    requests.api.request = request_with_ua

    # AKShare 1.18+ 新增 utils.request.request_with_retry 走 Session.get 绕过上面 patch；
    # 替换它走我们带 UA + Referer + trust_env=False 的长寿命 Session。
    def _patched_retry(url, params=None, timeout=15, **_kw):
        r = _get_eastmoney_session().get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r

    try:
        from akshare.utils import func as _ak_func
        from akshare.utils import request as _ak_req
        _ak_req.request_with_retry = _patched_retry
        _ak_func.request_with_retry = _patched_retry
    except ImportError:
        pass

    _patched = True


# import 时自动激活
patch_requests_ua()
