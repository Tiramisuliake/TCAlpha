"""A 股交易时段判断。"""
from __future__ import annotations

from datetime import datetime, time

import pytz

_CN_TZ = pytz.timezone("Asia/Shanghai")

MORNING_OPEN = time(9, 30)
MORNING_CLOSE = time(11, 30)
AFTERNOON_OPEN = time(13, 0)
AFTERNOON_CLOSE = time(15, 0)


def now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def is_trading_time(dt: datetime | None = None) -> bool:
    dt = dt or now_cn()
    if dt.weekday() >= 5:  # 周末
        return False
    t = dt.time()
    return (MORNING_OPEN <= t <= MORNING_CLOSE) or (AFTERNOON_OPEN <= t <= AFTERNOON_CLOSE)
