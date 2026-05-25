"""A 股代码工具：统一格式 / 交易所识别。

约定：项目内统一 sh600000 / sz000001 / bj430047（小写交易所前缀 + 6 位代码）。
"""
from __future__ import annotations


def normalize(symbol: str) -> str:
    """把 600000 / 600000.SH / sh.600000 等各种形式统一成 sh600000。"""
    s = symbol.strip().lower().replace(".", "").replace("-", "")
    if s.startswith(("sh", "sz", "bj")):
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("60", "68", "11", "13")):  # 沪市 + 沪科创板 + 转债
            return f"sh{s}"
        if s.startswith(("00", "30", "12")):  # 深市 + 创业板 + 转债
            return f"sz{s}"
        if s.startswith(("43", "83", "87", "92")):  # 北交所
            return f"bj{s}"
    raise ValueError(f"unknown symbol format: {symbol}")


def exchange(symbol: str) -> str:
    s = normalize(symbol)
    return s[:2].upper()


def code(symbol: str) -> str:
    s = normalize(symbol)
    return s[2:]
