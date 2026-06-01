"""A 股代码工具：统一格式 / 交易所识别。

约定：项目内统一 sh600000 / sz000001 / bj430047（小写交易所前缀 + 6 位代码）。
"""
from __future__ import annotations


def normalize(symbol: str) -> str:
    """把 600000 / 600000.SH / sh.600000 等各种形式统一成 sh600000。"""
    raw = symbol.strip().lower().replace("-", "")
    parts = raw.split(".")
    if len(parts) == 2:
        left, right = parts
        if left.isdigit() and len(left) == 6 and right in {"sh", "sz", "bj"}:
            return f"{right}{left}"
        if left in {"sh", "sz", "bj"} and right.isdigit() and len(right) == 6:
            return f"{left}{right}"

    s = raw.replace(".", "")
    if len(s) == 8 and s[:6].isdigit() and s[6:] in {"sh", "sz", "bj"}:
        return f"{s[6:]}{s[:6]}"
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
