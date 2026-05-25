"""回测引擎（Phase 3 实现）。

设计原则：复用 vnpy 的 BarData / ArrayManager / CtaTemplate，但不引入 EventEngine。
单 worker 进程内同步循环 on_bar，结果落 PG。
"""
from __future__ import annotations


def run(job_id: int) -> dict:
    raise NotImplementedError("Phase 3")
