"""注入合成日 K 到 ArcticDB（联调用，非生产代码）。

生成 200 根日 K，走势设计为：
  0..60: 缓慢下跌（fast MA 在 slow MA 之下，无信号）
  60..120: 上涨反转（fast MA 上穿 slow MA → 金叉）
  120..180: 高位震荡
  180..200: 下跌（fast MA 下穿 slow MA → 死叉）
warmup 拿最后 120 根（80..200），策略 state 应已捕获金叉/死叉走势。

用法（在 backend 目录）:
    uv run python scripts/inject_fake_kline.py
"""
from __future__ import annotations

import sys
from datetime import datetime

import numpy as np
import pandas as pd

# 让脚本能直接 import app.*
sys.path.insert(0, ".")

from app.services.data import save_daily  # noqa: E402

SYMBOL = "sh600000"
N_BARS = 200


def build_kline_df() -> pd.DataFrame:
    """合成 200 根日 K，覆盖最近 ~280 个自然日（去掉周末）。"""
    end = datetime.now().date()
    dates = pd.bdate_range(end=end, periods=N_BARS, freq="B")

    closes = np.zeros(N_BARS)
    base = 10.0
    for i in range(N_BARS):
        if i < 60:
            closes[i] = base - i * 0.02  # 缓慢下跌
        elif i < 120:
            closes[i] = closes[59] + (i - 59) * 0.05  # 反转上涨
        elif i < 180:
            closes[i] = closes[119] + np.sin((i - 119) * 0.3) * 0.3  # 高位震荡
        else:
            closes[i] = closes[179] - (i - 179) * 0.04  # 下跌

    df = pd.DataFrame(index=dates)
    df.index = df.index.tz_localize("Asia/Shanghai")
    df["close"] = closes
    df["open"] = closes * 0.998
    df["high"] = closes * 1.005
    df["low"] = closes * 0.995
    df["volume"] = np.random.uniform(1e6, 5e6, N_BARS)
    df["amount"] = df["close"] * df["volume"]
    return df[["open", "high", "low", "close", "volume", "amount"]].astype(float)


def main() -> None:
    df = build_kline_df()
    rows = save_daily(SYMBOL, df)
    print(f"injected {SYMBOL}: {rows} rows, "
          f"close range [{df['close'].min():.2f}, {df['close'].max():.2f}]")


if __name__ == "__main__":
    main()
