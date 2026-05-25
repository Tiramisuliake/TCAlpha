"""ArcticDB 单例封装（K 线 / Tick 时序数据）。

参考观澜 guanlan/core/trader/database/arctic.py 的思路：单例 + 懒加载。
Phase 0 只提供句柄，Phase 1 再写读写函数。
"""
from __future__ import annotations

from threading import Lock
from typing import Any

from app.config import settings

_lock = Lock()
_arctic: Any | None = None


def get_arctic() -> Any:
    """获取 Arctic 实例（懒加载 + 线程安全）。"""
    global _arctic
    if _arctic is not None:
        return _arctic
    with _lock:
        if _arctic is None:
            from arcticdb import Arctic  # 延迟导入，避免无 LMDB 时启动报错

            _arctic = Arctic(settings.arctic_uri)
    return _arctic


def get_library(name: str) -> Any:
    """获取或创建一个 library。常用 name：bar_1m / bar_1d / tick"""
    ac = get_arctic()
    if name not in ac.list_libraries():
        ac.create_library(name)
    return ac.get_library(name)
