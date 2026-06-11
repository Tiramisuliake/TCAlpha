"""回测引擎（Phase 3）。

流程：
  BacktestJob (PG) → 读 ArcticDB K 线 → strategy.on_bar(bar)
  → 撮合（next bar 开盘价）→ 收集 trade → 算指标
  → 写 PG (result + BacktestTrade)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

# ── 中间数据结构 ──────────────────────────────────────────────────────

@dataclass
class PendingOrder:
    direction: str   # long / short
    offset: str      # open / close
    volume: int


@dataclass
class Trade:
    dt: datetime
    direction: str
    offset: str
    price: float
    volume: int
    commission: float
    pnl: float | None = None
    symbol: str = ""  # 多标的（轮动）回测时记录各自标的；单标的为空，落库时回退 job.symbol


# ── 策略类注册表 ──────────────────────────────────────────────────────

STRATEGY_CLASSES: dict[str, type] = {}


def _load_strategy_classes() -> None:
    if STRATEGY_CLASSES:
        return
    from app.strategies.examples.atr_stop import AtrStopStrategy
    from app.strategies.examples.boll import BollStrategy
    from app.strategies.examples.boll_squeeze import BollSqueezeStrategy
    from app.strategies.examples.dmi import DmiStrategy
    from app.strategies.examples.grid import GridStrategy
    from app.strategies.examples.kdj import KdjStrategy
    from app.strategies.examples.ma_cross import MaCrossStrategy
    from app.strategies.examples.ma_vol import MaVolStrategy
    from app.strategies.examples.macd import MacdStrategy
    from app.strategies.examples.pullback import PullbackStrategy
    from app.strategies.examples.rsi import RsiStrategy
    from app.strategies.examples.turtle import TurtleStrategy
    STRATEGY_CLASSES["MaCrossStrategy"] = MaCrossStrategy
    STRATEGY_CLASSES["MacdStrategy"] = MacdStrategy
    STRATEGY_CLASSES["RsiStrategy"] = RsiStrategy
    STRATEGY_CLASSES["BollStrategy"] = BollStrategy
    STRATEGY_CLASSES["TurtleStrategy"] = TurtleStrategy
    STRATEGY_CLASSES["KdjStrategy"] = KdjStrategy
    STRATEGY_CLASSES["GridStrategy"] = GridStrategy
    STRATEGY_CLASSES["DmiStrategy"] = DmiStrategy
    STRATEGY_CLASSES["AtrStopStrategy"] = AtrStopStrategy
    STRATEGY_CLASSES["MaVolStrategy"] = MaVolStrategy
    STRATEGY_CLASSES["PullbackStrategy"] = PullbackStrategy
    STRATEGY_CLASSES["BollSqueezeStrategy"] = BollSqueezeStrategy


def get_strategy_class(class_name: str) -> type:
    _load_strategy_classes()
    cls = STRATEGY_CLASSES.get(class_name)
    if not cls:
        raise ValueError(f"unknown strategy class: {class_name}")
    return cls


def list_strategy_classes() -> list[dict]:
    _load_strategy_classes()
    result = []
    for name, cls in STRATEGY_CLASSES.items():
        # 收集参数定义
        params_schema = {}
        params = getattr(cls, "params", None)
        if params is not None and hasattr(params, "model_fields"):
            for fname, finfo in cast_model_fields(params).items():
                minimum, maximum = _field_bounds(finfo)
                params_schema[fname] = {
                    "title": finfo.title or fname,
                    "default": finfo.default,
                    "type": str(finfo.annotation),
                    "minimum": minimum,
                    "maximum": maximum,
                }
        result.append({
            "class_name": name,
            "author": getattr(cls, "author", ""),
            "params_schema": params_schema,
        })
    return result


def cast_model_fields(model: Any) -> dict[str, Any]:
    return model.model_fields


def _field_bounds(finfo: Any) -> tuple[float | None, float | None]:
    """从 Pydantic FieldInfo.metadata 提取 ge/gt（下界）与 le/lt（上界），供前端表单约束。"""
    import annotated_types as at

    minimum = maximum = None
    for meta in getattr(finfo, "metadata", []):
        if isinstance(meta, at.Ge):
            minimum = meta.ge
        elif isinstance(meta, at.Gt):
            minimum = meta.gt
        elif isinstance(meta, at.Le):
            maximum = meta.le
        elif isinstance(meta, at.Lt):
            maximum = meta.lt
    return minimum, maximum


# ── K 线加载 ──────────────────────────────────────────────────────────

def _load_bars(symbol: str, start: str, end: str) -> list:
    """从 ArcticDB 读取日 K，转换为 vnpy BarData 列表。"""
    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import BarData

    from app.db.arctic import get_library
    from app.utils.symbol import normalize

    sym_key = normalize(symbol)
    lib = get_library("bar_1d")
    if sym_key not in lib.list_symbols():
        return []

    df = lib.read(sym_key).data
    # 按日期过滤（兼容 tz-aware 与 tz-naive index）
    tz = df.index.tz
    start_ts = pd.Timestamp(start, tz=tz) if tz is not None else pd.Timestamp(start)
    end_ts = pd.Timestamp(end, tz=tz) if tz is not None else pd.Timestamp(end)
    df = df[(df.index >= start_ts) & (df.index <= end_ts)]
    if df.empty:
        return []

    exchange = Exchange.SSE if symbol.startswith("sh") else Exchange.SZSE
    bars = []
    for ts, row in df.iterrows():
        bars.append(
            BarData(
                symbol=sym_key,
                exchange=exchange,
                datetime=ts.to_pydatetime().replace(tzinfo=UTC),
                interval=Interval.DAILY,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row["volume"]),
                turnover=float(row.get("amount", 0)),
                gateway_name="BACKTEST",
            )
        )
    return bars


# ── 基准指数（回测对比） ──────────────────────────────────────────────

_DEFAULT_BENCHMARK = "000300"
_BENCHMARK_INDICES = {
    "000300": "沪深300",
    "000905": "中证500",
    "399006": "创业板指",
    "000016": "上证50",
}


def _benchmark_name(code: str) -> str:
    return _BENCHMARK_INDICES.get(code, code)


def _load_index_close(index_code: str, start: str, end: str) -> pd.Series:
    """加载基准指数收盘价序列（ArcticDB ``index_1d`` 缓存；缺失或未覆盖区间则 lazy 下载）。

    基准是可选增强，任何失败都返回空 Series，绝不能拖垮主回测。
    """
    try:
        from app.db.arctic import get_library

        lib = get_library("index_1d")
        df = None
        need_download = index_code not in lib.list_symbols()
        if not need_download:
            df = lib.read(index_code).data
            tz = df.index.tz
            s_ts = pd.Timestamp(start, tz=tz) if tz is not None else pd.Timestamp(start)
            e_ts = pd.Timestamp(end, tz=tz) if tz is not None else pd.Timestamp(end)
            # 库内数据未完整覆盖请求区间 → 重新下载覆盖
            if df.empty or df.index.min() > s_ts or df.index.max() < e_ts:
                need_download = True
        if need_download:
            from app.data.provider import get_provider

            df = get_provider().fetch_index_daily(index_code, start, end)
            lib.write(index_code, df)
            logger.info("benchmark index {} downloaded: {} rows", index_code, len(df))

        tz = df.index.tz
        s_ts = pd.Timestamp(start, tz=tz) if tz is not None else pd.Timestamp(start)
        e_ts = pd.Timestamp(end, tz=tz) if tz is not None else pd.Timestamp(end)
        df = df[(df.index >= s_ts) & (df.index <= e_ts)]
        if "close" not in df.columns or df.empty:
            return pd.Series(dtype=float)
        return df["close"]
    except Exception as exc:
        logger.warning("load benchmark index {} failed (skip benchmark): {}", index_code, exc)
        return pd.Series(dtype=float)


# ── 撮合 ──────────────────────────────────────────────────────────────

def _limit_pct(symbol: str) -> float:
    """A 股涨跌停比例（按板块）：创业板(300/301)/科创板(688) 20%，北交所 30%，主板 10%。

    ST 需股票名判定，回测无名称，暂按板块比例处理（不单独 5%）。
    """
    s = symbol.lower()
    raw = s[2:] if s[:2] in ("sh", "sz", "bj") else s
    if s.startswith("bj") or raw.startswith(("8", "4")):
        return 0.30
    if raw.startswith(("300", "301", "688")):
        return 0.20
    return 0.10


def _match_orders(
    pending: list[PendingOrder],
    next_bar,
    commission_rate: float,
    slippage: float,
    pos: int,
    prev_close: float | None = None,
    symbol: str = "",
) -> tuple[list[Trade], int]:
    """用下一根 bar 的开盘价撮合，返回成交列表和新持仓。

    A 股约束：停牌（volume==0）不成交；一字涨停（最低价≥涨停价）买不进；
    一字跌停（最高价≤跌停价）卖不出。涨跌停价由 prev_close 按板块比例推算
    （prev_close 为 None 时不做涨跌停约束，向后兼容）。
    """
    trades: list[Trade] = []

    # 停牌：当日无成交，挂单无法撮合
    if getattr(next_bar, "volume", 0) == 0:
        return trades, pos

    up_limit = down_limit = None
    if prev_close:
        pct = _limit_pct(symbol)
        up_limit = round(prev_close * (1 + pct), 2)
        down_limit = round(prev_close * (1 - pct), 2)

    for order in pending:
        if order.offset == "open":
            # 一字涨停：开盘即封死，买不进
            if up_limit is not None and next_bar.low_price >= up_limit:
                continue
            exec_price = next_bar.open_price + (slippage if order.direction == "long" else -slippage)
            commission = exec_price * order.volume * commission_rate
            trades.append(Trade(
                dt=next_bar.datetime,
                direction=order.direction,
                offset="open",
                price=exec_price,
                volume=order.volume,
                commission=commission,
            ))
            pos += order.volume if order.direction == "long" else -order.volume
        else:  # close
            vol = min(order.volume, abs(pos))
            if vol <= 0:
                continue
            # 一字跌停：卖不出
            if down_limit is not None and next_bar.high_price <= down_limit:
                continue
            exec_price = next_bar.open_price - (slippage if order.direction == "long" else -slippage)
            commission = exec_price * vol * commission_rate
            # A 股卖出加印花税
            stamp_duty = exec_price * vol * 0.001
            trades.append(Trade(
                dt=next_bar.datetime,
                direction=order.direction,
                offset="close",
                price=exec_price,
                volume=vol,
                commission=commission + stamp_duty,
            ))
            pos -= vol if order.direction == "long" else -vol
    return trades, pos


# ── 资金曲线 & 指标 ───────────────────────────────────────────────────

def _settle(trades: list[Trade], bars: list, init_capital: float) -> pd.Series:
    """构造每日资金曲线。"""
    if not bars:
        return pd.Series([init_capital], index=[datetime.now(tz=UTC)])

    cash = init_capital
    pos = 0
    avg_price = 0.0
    equity_values: list[float] = []
    equity_dates: list[datetime] = []

    # 标记每个 bar 对应的成交
    trade_map: dict[datetime, list[Trade]] = {}
    for t in trades:
        trade_map.setdefault(t.dt, []).append(t)

    for bar in bars:
        for t in trade_map.get(bar.datetime, []):
            if t.offset == "open":
                cash -= t.price * t.volume + t.commission
                total_cost = avg_price * pos + t.price * t.volume
                pos += t.volume
                avg_price = total_cost / pos if pos > 0 else 0.0
            else:
                pnl = (t.price - avg_price) * t.volume - t.commission
                t.pnl = pnl
                cash += t.price * t.volume - t.commission
                pos -= t.volume
                if pos == 0:
                    avg_price = 0.0

        market_value = pos * bar.close_price
        equity_values.append(cash + market_value)
        equity_dates.append(bar.datetime)

    return pd.Series(equity_values, index=pd.DatetimeIndex(equity_dates))


def _drawdown_interval(equity: pd.Series) -> dict:
    """最大回撤区间：峰值日 → 谷底日 → 修复日（首次回到峰值）+ 峰→谷持续天数。

    无回撤（资金单调不降）时四项均退化为 None / 0。修复日为 None 表示截止回测
    结束仍未回到前高（still underwater）。
    """
    empty = {"max_dd_start": None, "max_dd_end": None, "max_dd_recovery": None, "max_dd_days": 0}
    if len(equity) < 2:
        return empty
    cum_max = equity.cummax()
    drawdown = (equity - cum_max) / cum_max
    trough_idx = drawdown.idxmin()
    if float(drawdown.loc[trough_idx]) >= 0:
        return empty

    peak_value = float(cum_max.loc[trough_idx])
    pre = equity.loc[:trough_idx]
    peak_idx = pre[pre >= peak_value].index[0]
    post = equity.loc[trough_idx:]
    recovered = post[post >= peak_value]
    recovery_idx = recovered.index[0] if len(recovered) else None

    def _d(x: Any) -> str | None:
        if x is None:
            return None
        return str(x.date()) if hasattr(x, "date") else str(x)

    return {
        "max_dd_start": _d(peak_idx),
        "max_dd_end": _d(trough_idx),
        "max_dd_recovery": _d(recovery_idx),
        "max_dd_days": int((trough_idx - peak_idx).days),
    }


def _streaks(trades: list[Trade]) -> tuple[int, int]:
    """最长连胜 / 连亏（按平仓盈亏的时间顺序，trades 已是时序追加）。"""
    max_win = max_lose = cur_win = cur_lose = 0
    for t in trades:
        if t.pnl is None:
            continue
        if t.pnl > 0:
            cur_win, cur_lose = cur_win + 1, 0
            max_win = max(max_win, cur_win)
        elif t.pnl < 0:
            cur_lose, cur_win = cur_lose + 1, 0
            max_lose = max(max_lose, cur_lose)
    return max_win, max_lose


def _monthly_returns(equity: pd.Series, init_capital: float) -> list[dict]:
    """月度收益序列（按月末资金 pct_change；首月以 init_capital 为基）。"""
    if len(equity) < 2:
        return []
    eq = equity.copy()
    eq.index = pd.DatetimeIndex(eq.index).tz_localize(None)
    m = eq.resample("ME").last()
    if m.empty:
        return []
    prev = m.shift(1)
    prev.iloc[0] = init_capital
    mret = (m / prev - 1).replace([np.inf, -np.inf], np.nan).dropna()
    return [{"month": d.strftime("%Y-%m"), "value": round(float(v), 4)} for d, v in mret.items()]


def _rolling_sharpe(rets: pd.Series, window: int = 60) -> list[dict]:
    """滚动年化夏普（默认 60 交易日窗口）。序列短于窗口则返回空。"""
    if len(rets) < window:
        return []
    mean = rets.rolling(window).mean()
    std = rets.rolling(window).std()
    rs = (mean / std * np.sqrt(252)).replace([np.inf, -np.inf], np.nan).dropna()
    idx = pd.DatetimeIndex(rs.index).tz_localize(None)
    return [
        {"dt": str(d.date()), "value": round(float(v), 4)}
        for d, v in zip(idx, rs.values, strict=False)
    ]


def _round_trips(trades: list[Trade], bars: list | None = None) -> list[dict]:
    """把时序 open/close 成交配对为「回合」，按 (symbol, direction) 分腿独立跟踪。

    单标的只做多时退化为原行为；轮动（多 symbol 串行）与配对（多空两腿
    交织）同样配对正确。持仓均价跟踪与 _settle 一致（加权摊薄，清仓归零），
    pnl 直接复用已填好的 Trade.pnl。MAE/MFE 需要 bars 提供持仓期间高低价
    （仅单标的回测传入）；空头腿语义取反：期间最高价为最不利、最低价为最有利。
    """
    idx_of: dict[datetime, int] = (
        {b.datetime: i for i, b in enumerate(bars)} if bars else {}
    )

    legs: dict[tuple[str, str], dict] = {}
    rts: list[dict] = []

    for t in trades:
        leg = legs.setdefault((t.symbol, t.direction), {"pos": 0, "avg": 0.0, "entry_dt": None})
        if t.offset == "open":
            if leg["pos"] == 0:
                leg["entry_dt"] = t.dt
            total_cost = leg["avg"] * leg["pos"] + t.price * t.volume
            leg["pos"] += t.volume
            leg["avg"] = total_cost / leg["pos"] if leg["pos"] > 0 else 0.0
            continue

        # close：在本腿内配一个回合
        if leg["pos"] <= 0 or leg["entry_dt"] is None:
            continue
        avg_price: float = leg["avg"]
        entry_dt: datetime = leg["entry_dt"]
        cost = avg_price * t.volume
        ret = float(t.pnl) / cost if t.pnl is not None and cost > 0 else None

        mae = mfe = None
        if bars and avg_price > 0 and entry_dt in idx_of and t.dt in idx_of:
            window = bars[idx_of[entry_dt]: idx_of[t.dt] + 1]
            lo = min(b.low_price for b in window)
            hi = max(b.high_price for b in window)
            if t.direction == "long":
                mae = round(lo / avg_price - 1, 4)
                mfe = round(hi / avg_price - 1, 4)
            else:
                mae = round(1 - hi / avg_price, 4)
                mfe = round(1 - lo / avg_price, 4)

        rts.append({
            "entry_dt": str(entry_dt.date()),
            "exit_dt": str(t.dt.date()),
            "holding_days": (t.dt - entry_dt).days,
            "entry_price": round(avg_price, 4),
            "exit_price": round(t.price, 4),
            "volume": t.volume,
            "pnl": round(float(t.pnl), 2) if t.pnl is not None else None,
            "return_pct": round(ret, 4) if ret is not None else None,
            "mae": mae,
            "mfe": mfe,
            "symbol": t.symbol,
            "direction": t.direction,
        })
        leg["pos"] -= t.volume
        if leg["pos"] == 0:
            leg["avg"] = 0.0
            leg["entry_dt"] = None
    return rts


def _metrics(
    equity: pd.Series,
    trades: list[Trade],
    init_capital: float,
    benchmark_close: pd.Series | None = None,
    benchmark_name: str = "基准",
    bars: list | None = None,
) -> dict:
    rets = equity.pct_change().dropna()
    total_return = float(equity.iloc[-1] / init_capital - 1)
    days = (equity.index[-1] - equity.index[0]).days
    annual_return = float((1 + total_return) ** (252 / max(days, 1)) - 1) if days > 0 else 0.0

    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    downside = rets[rets < 0]
    sortino = float(rets.mean() / downside.std() * np.sqrt(252)) if len(downside) and downside.std() > 0 else 0.0

    cum_max = equity.cummax()
    drawdown = (equity - cum_max) / cum_max
    max_dd = float(drawdown.min())

    closed_pnls = [float(t.pnl) for t in trades if t.pnl is not None]
    wins = [pnl for pnl in closed_pnls if pnl > 0]
    losses = [pnl for pnl in closed_pnls if pnl < 0]
    win_rate = len(wins) / len(closed_pnls) if closed_pnls else 0.0
    losing_pnl = sum(losses)
    profit_factor = (
        sum(wins) / abs(losing_pnl)
        if losing_pnl < 0 else float("inf")
    )
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    max_win_streak, max_lose_streak = _streaks(trades)

    # 风险：年化波动率 + Calmar（年化收益 / |最大回撤|）
    volatility = float(rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    calmar = float(annual_return / abs(max_dd)) if max_dd < 0 else 0.0

    # 交易级分析：回合配对 + 持仓周期 + MAE/MFE + 单笔期望
    round_trips = _round_trips(trades, bars)
    holding = [r["holding_days"] for r in round_trips]
    win_holding = [r["holding_days"] for r in round_trips if (r["pnl"] or 0) > 0]
    lose_holding = [r["holding_days"] for r in round_trips if (r["pnl"] or 0) < 0]
    maes = [r["mae"] for r in round_trips if r["mae"] is not None]
    mfes = [r["mfe"] for r in round_trips if r["mfe"] is not None]
    # 单笔期望盈亏（元）：胜率×平均盈利 + 败率×平均亏损（avg_loss 为负）
    expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

    # 资金曲线（按日期 → ISO 字符串，前端用）
    equity_curve = [
        {"dt": str(dt.date() if hasattr(dt, "date") else dt), "value": float(v)}
        for dt, v in zip(equity.index, equity.values, strict=False)
    ]

    out = {
        "total_return": round(total_return, 4),
        "annual_return": round(annual_return, 4),
        "sharpe": round(sharpe, 4),
        "sortino": round(sortino, 4),
        "max_drawdown": round(max_dd, 4),
        "trade_count": len(closed_pnls),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 9999.0,
        "init_capital": init_capital,
        "final_equity": round(float(equity.iloc[-1]), 2),
        "equity_curve": equity_curve,
        # ── 绩效深化（v0.8.x）：风险标量 + 收益分布 ──
        "calmar": round(calmar, 4),
        "volatility": round(volatility, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_win_streak": max_win_streak,
        "max_lose_streak": max_lose_streak,
        **_drawdown_interval(equity),
        "monthly_returns": _monthly_returns(equity, init_capital),
        "rolling_sharpe": _rolling_sharpe(rets),
        # ── 交易明细深化（v0.8.3）：回合 + 持仓周期 + MAE/MFE + 期望 ──
        "round_trips": round_trips,
        "avg_holding_days": round(float(np.mean(holding)), 1) if holding else 0.0,
        "win_holding_days": round(float(np.mean(win_holding)), 1) if win_holding else 0.0,
        "lose_holding_days": round(float(np.mean(lose_holding)), 1) if lose_holding else 0.0,
        "avg_mae": round(float(np.mean(maes)), 4) if maes else None,
        "avg_mfe": round(float(np.mean(mfes)), 4) if mfes else None,
        "expectancy": round(expectancy, 2),
    }
    if benchmark_close is not None and not benchmark_close.empty:
        out.update(_benchmark_metrics(equity, benchmark_close, init_capital, benchmark_name))
    return out


def _benchmark_metrics(
    equity: pd.Series, benchmark_close: pd.Series, init_capital: float, benchmark_name: str = "基准"
) -> dict:
    """对齐基准到策略交易日，算 Alpha / Beta / 超额收益 / 信息比率 + 归一化基准曲线。

    两边时区语义不同（equity 的 index 被标成 UTC、基准是 Asia/Shanghai），
    统一抹掉 tz 并按自然日对齐，避免错位；基准缺口前向填充（指数极少停牌）。
    """
    if benchmark_close is None or benchmark_close.empty or len(equity) < 2:
        return {}

    eq = equity.copy()
    eq.index = pd.DatetimeIndex(eq.index).tz_localize(None).normalize()
    eq = eq[~eq.index.duplicated(keep="last")]

    bench = benchmark_close.copy()
    bench.index = pd.DatetimeIndex(bench.index).tz_localize(None).normalize()
    bench = bench[~bench.index.duplicated(keep="last")]
    bench = bench.reindex(eq.index).ffill().bfill()
    if bench.isna().any() or len(bench) < 2 or float(bench.iloc[0]) == 0:
        return {}

    init = float(eq.iloc[0]) or init_capital
    bench_norm = bench / float(bench.iloc[0]) * init

    total_return = float(eq.iloc[-1] / init - 1)
    bench_return = float(bench.iloc[-1] / bench.iloc[0] - 1)

    sr = eq.pct_change().dropna()
    br = bench.pct_change().dropna()
    common = sr.index.intersection(br.index)
    sr = sr.reindex(common)
    br = br.reindex(common)

    var_b = float(br.var())
    beta = float(np.cov(sr, br)[0, 1] / var_b) if var_b > 0 and len(common) > 1 else 0.0
    alpha = float((sr.mean() - beta * br.mean()) * 252)

    active = sr - br
    tracking_error = float(active.std() * np.sqrt(252))
    information_ratio = (
        float(active.mean() * 252 / tracking_error) if tracking_error > 0 else 0.0
    )

    # 滚动 Beta（60 交易日窗口）：cov(策略,基准)/var(基准)
    window = 60
    rolling_beta: list[dict] = []
    if len(common) >= window:
        cov = sr.rolling(window).cov(br)
        var = br.rolling(window).var().replace(0, np.nan)
        rb = (cov / var).replace([np.inf, -np.inf], np.nan).dropna()
        rb_idx = pd.DatetimeIndex(rb.index).tz_localize(None)
        rolling_beta = [
            {"dt": str(d.date()), "value": round(float(v), 4)}
            for d, v in zip(rb_idx, rb.values, strict=False)
        ]

    # 相对强弱：策略归一 / 基准归一（>1 跑赢基准，<1 跑输）
    rel = (eq / float(eq.iloc[0])) / (bench / float(bench.iloc[0]))
    rel = rel.replace([np.inf, -np.inf], np.nan).dropna()
    relative_strength = [
        {"dt": str(d.date()), "value": round(float(v), 4)}
        for d, v in zip(rel.index, rel.values, strict=False)
    ]

    bench_curve = [
        {"dt": str(d.date()), "value": round(float(v), 2)}
        for d, v in zip(bench_norm.index, bench_norm.values, strict=False)
    ]
    return {
        "benchmark": benchmark_name,
        "benchmark_return": round(bench_return, 4),
        "excess_return": round(total_return - bench_return, 4),
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        "information_ratio": round(information_ratio, 4),
        "benchmark_curve": bench_curve,
        "rolling_beta": rolling_beta,
        "relative_strength": relative_strength,
    }


# ── 纯回测 + 网格扫参 ─────────────────────────────────────────────────

def _simulate(
    bars: list,
    symbol: str,
    class_name: str,
    params: dict,
    init_capital: float,
    commission_rate: float,
    slippage: float,
    benchmark_close: pd.Series | None = None,
    benchmark_name: str = "基准",
) -> tuple[dict, list[Trade]]:
    """纯回测：实例化策略 → 逐 bar 撮合（next bar 开盘价）→ 算指标。

    返回 (metrics, trades)。不依赖 BacktestJob，供 run() 与 run_sweep() 共用。
    """
    cls = get_strategy_class(class_name)
    strategy = cls(symbol, params)

    all_trades: list[Trade] = []
    pos = 0
    pending: list[PendingOrder] = []

    for i, bar in enumerate(bars[:-1]):
        if pending:
            prev_close = bars[i - 1].close_price if i >= 1 else None
            new_trades, pos = _match_orders(
                pending, bar, commission_rate, slippage, pos, prev_close, symbol
            )
            all_trades.extend(new_trades)
            strategy.state.pos = pos
            pending = []

        strategy.on_bar(bar)

        sig = getattr(strategy, "_pending_signal", None)
        if sig:
            direction, offset, volume = sig
            pending.append(PendingOrder(direction=direction, offset=offset, volume=volume))
            strategy._pending_signal = None

    if pending and len(bars) >= 2:
        new_trades, pos = _match_orders(
            pending, bars[-1], commission_rate, slippage, pos, bars[-2].close_price, symbol
        )
        all_trades.extend(new_trades)

    equity = _settle(all_trades, bars, init_capital)
    result = _metrics(equity, all_trades, init_capital, benchmark_close, benchmark_name, bars=bars)
    return result, all_trades


_SWEEP_METRIC_KEYS = (
    "total_return",
    "annual_return",
    "sharpe",
    "max_drawdown",
    "win_rate",
    "trade_count",
    # v0.8.5：寻优目标接入绩效深化指标
    "calmar",
    "expectancy",
)


def run_sweep(
    symbol: str,
    class_name: str,
    param_grid: dict[str, list],
    start: str,
    end: str,
    init_capital: float,
    commission_rate: float,
    slippage: float,
    target: str = "sharpe",
) -> dict:
    """网格扫参：对 param_grid 的笛卡尔积逐组回测，按 target 降序排序。

    K 线只加载一次；每组参数复用 _simulate。返回 {results, best, ...}。
    """
    import itertools

    bars = _load_bars(symbol, start, end)
    if len(bars) < 2:
        raise RuntimeError(f"insufficient bars for {symbol}: {len(bars)}")

    keys = list(param_grid.keys())
    combos = list(itertools.product(*[param_grid[k] for k in keys]))

    results: list[dict] = []
    for combo in combos:
        params = dict(zip(keys, combo, strict=False))
        metrics, _ = _simulate(
            bars, symbol, class_name, params, init_capital, commission_rate, slippage
        )
        results.append(
            {"params": params, "metrics": {k: metrics[k] for k in _SWEEP_METRIC_KEYS}}
        )

    # 所有目标指标均"越大越好"（max_drawdown 为负，越接近 0 越大）
    results.sort(key=lambda r: r["metrics"].get(target, 0) or 0, reverse=True)
    return {
        "target": target,
        "param_keys": keys,
        "count": len(results),
        "results": results,
        "best": results[0] if results else None,
    }


# ── 多标的动量轮动（v0.8.5） ──────────────────────────────────────────

ROTATION_CLASS = "RotationBacktest"  # run() 按此 class_name 走轮动分支（不进策略注册表）


def _load_aligned_frames(symbols: list[str], start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把多标的日 K 对齐到交易日并集，返回 (开盘价表, 收盘价表)。

    收盘缺口前向填充（停牌延用前收）；开盘缺口用收盘兜底。index 统一抹 tz
    并归一到自然日，避免多标的时区/时刻不一致导致错位。
    """
    from app.db.arctic import get_library
    from app.utils.symbol import normalize

    lib = get_library("bar_1d")
    opens: dict[str, pd.Series] = {}
    closes: dict[str, pd.Series] = {}
    for sym in symbols:
        key = normalize(sym)
        if key not in lib.list_symbols():
            logger.warning("rotation: symbol {} not in arctic, skipped", key)
            continue
        df = lib.read(key).data
        tz = df.index.tz
        s_ts = pd.Timestamp(start, tz=tz) if tz is not None else pd.Timestamp(start)
        e_ts = pd.Timestamp(end, tz=tz) if tz is not None else pd.Timestamp(end)
        df = df[(df.index >= s_ts) & (df.index <= e_ts)]
        if df.empty:
            continue
        idx = pd.DatetimeIndex(df.index).tz_localize(None).normalize()
        opens[key] = pd.Series(df["open"].to_numpy(dtype=float), index=idx)
        closes[key] = pd.Series(df["close"].to_numpy(dtype=float), index=idx)

    if not closes:
        return pd.DataFrame(), pd.DataFrame()
    close_df = pd.DataFrame(closes).sort_index().ffill()
    open_df = pd.DataFrame(opens).sort_index()
    open_df = open_df.fillna(close_df)
    return open_df, close_df


def run_rotation(
    symbols: list[str],
    start: str,
    end: str,
    init_capital: float,
    commission_rate: float,
    slippage: float,
    lookback: int = 60,
    rebalance_days: int = 20,
    benchmark_close: pd.Series | None = None,
    benchmark_name: str = "基准",
) -> tuple[dict, list[Trade]]:
    """动量轮动：每 rebalance_days 个交易日按过去 lookback 日收益率排名，
    全仓持有最强标的；动量全为负则空仓（绝对动量过滤，熊市离场）。

    信号在第 t 日收盘计算，第 t+1 日开盘价 ± slippage 撮合（与单标的引擎
    一致，无未来函数）。买入按一手（100 股）取整，余款留现金；卖出含印花税。
    返回 (metrics, trades)，trades 各自带 symbol。
    """
    open_df, close_df = _load_aligned_frames(symbols, start, end)
    n = len(close_df)
    if close_df.empty or n < lookback + 2:
        raise RuntimeError(f"insufficient bars for rotation: {n} (need > lookback {lookback})")

    dates = close_df.index
    dates_utc = dates.tz_localize(UTC)
    momentum = close_df / close_df.shift(lookback) - 1

    cash = init_capital
    pos = 0
    holding: str | None = None
    avg_price = 0.0
    trades: list[Trade] = []
    holdings_log: list[dict] = []
    equity_vals: list[float] = []
    switch_to: str | None = None
    switch_pending = False

    for i in range(n):
        dt = dates_utc[i].to_pydatetime()

        # 1) 执行昨日收盘决定的调仓（今日开盘价撮合）
        if switch_pending:
            if holding is not None and pos > 0:
                price = float(open_df.iloc[i][holding]) - slippage
                commission = price * pos * commission_rate + price * pos * 0.001  # 含印花税
                pnl = (price - avg_price) * pos - commission
                cash += price * pos - commission
                trades.append(Trade(
                    dt=dt, direction="long", offset="close", price=price,
                    volume=pos, commission=commission, pnl=pnl, symbol=holding,
                ))
                pos, avg_price, holding = 0, 0.0, None
            if switch_to is not None:
                price = float(open_df.iloc[i][switch_to]) + slippage
                volume = int(cash // (price * 100)) * 100  # 一手取整
                if volume > 0:
                    commission = price * volume * commission_rate
                    cash -= price * volume + commission
                    trades.append(Trade(
                        dt=dt, direction="long", offset="open", price=price,
                        volume=volume, commission=commission, symbol=switch_to,
                    ))
                    pos, avg_price, holding = volume, price, switch_to
            holdings_log.append({"dt": str(dates[i].date()), "symbol": holding or ""})
            switch_pending, switch_to = False, None

        # 2) 收盘 mark-to-market
        market_value = pos * float(close_df.iloc[i][holding]) if holding else 0.0
        equity_vals.append(cash + market_value)

        # 3) 调仓日收盘：算动量、定下期目标（次日开盘执行）
        if i >= lookback and i % rebalance_days == 0 and i < n - 1:
            row = momentum.iloc[i].dropna()
            if not row.empty:
                best = str(row.idxmax())
                target = best if float(row.max()) > 0 else None
            else:
                target = None
            if target != holding:
                switch_pending, switch_to = True, target

    equity = pd.Series(equity_vals, index=dates_utc)
    result = _metrics(equity, trades, init_capital, benchmark_close, benchmark_name)
    result["rotation_symbols"] = list(close_df.columns)
    result["rotation_holdings"] = holdings_log
    result["rotation_lookback"] = lookback
    result["rotation_rebalance_days"] = rebalance_days
    return result, trades


# ── 配对交易（v0.8.6，统计套利，含模拟做空腿） ─────────────────────────

PAIR_CLASS = "PairTradingBacktest"  # run() 按此 class_name 走配对分支


def run_pair(
    symbol_a: str,
    symbol_b: str,
    start: str,
    end: str,
    init_capital: float,
    commission_rate: float,
    slippage: float,
    window: int = 60,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    benchmark_close: pd.Series | None = None,
    benchmark_name: str = "基准",
) -> tuple[dict, list[Trade]]:
    """配对交易：价差 = ln(A) - ln(B)，滚动 window 日均值/标准差算 z-score。

    z > entry_z → 空 A 多 B（A 相对走强过头）；z < -entry_z → 多 A 空 B；
    |z| < exit_z（价差回归）→ 双腿平仓。多空各半仓名义，信号收盘算、
    次日开盘 ± 滑点撮合（无未来函数）。

    做空为模拟语义（融券简化）：卖空收现金、负债按现价 mark-to-market、
    全额名义无杠杆；A 股实盘融券的券源 / 保证金 / 费率约束此处不建模。
    """
    from app.utils.symbol import normalize

    sym_a, sym_b = normalize(symbol_a), normalize(symbol_b)
    open_df, close_df = _load_aligned_frames([sym_a, sym_b], start, end)
    n = len(close_df)
    if close_df.empty or sym_a not in close_df.columns or sym_b not in close_df.columns:
        raise RuntimeError(f"pair requires both symbols in arctic: {sym_a}, {sym_b}")
    if n < window + 2:
        raise RuntimeError(f"insufficient bars for pair: {n} (need > window {window})")

    dates = close_df.index
    dates_utc = dates.tz_localize(UTC)
    spread = np.log(close_df[sym_a]) - np.log(close_df[sym_b])
    z = (spread - spread.rolling(window).mean()) / spread.rolling(window).std()

    cash = init_capital
    side = 0  # 0 空仓 / +1 多A空B / -1 空A多B
    long_sym = short_sym = ""
    long_vol = short_vol = 0
    long_avg = short_avg = 0.0
    trades: list[Trade] = []
    equity_vals: list[float] = []
    pending: int | None = None  # 次日开盘要切换到的 side

    def _open_pair(i: int, new_side: int) -> None:
        nonlocal cash, side, long_sym, short_sym, long_vol, short_vol, long_avg, short_avg
        dt = dates_utc[i].to_pydatetime()
        lsym, ssym = (sym_a, sym_b) if new_side == 1 else (sym_b, sym_a)
        notional = cash / 2
        lp = float(open_df.iloc[i][lsym]) + slippage
        sp = float(open_df.iloc[i][ssym]) - slippage
        lvol = int(notional // (lp * 100)) * 100
        svol = int(notional // (sp * 100)) * 100
        if lvol <= 0 or svol <= 0:
            return  # 资金不足以双腿成对开仓，放弃本次信号
        lcomm = lp * lvol * commission_rate
        scomm = sp * svol * commission_rate + sp * svol * 0.001  # 卖空=卖出，含印花税
        cash -= lp * lvol + lcomm
        cash += sp * svol - scomm
        trades.append(Trade(dt=dt, direction="long", offset="open", price=lp,
                            volume=lvol, commission=lcomm, symbol=lsym))
        trades.append(Trade(dt=dt, direction="short", offset="open", price=sp,
                            volume=svol, commission=scomm, symbol=ssym))
        long_sym, short_sym = lsym, ssym
        long_vol, short_vol = lvol, svol
        long_avg, short_avg = lp, sp
        side = new_side

    def _close_pair(i: int) -> None:
        nonlocal cash, side, long_sym, short_sym, long_vol, short_vol, long_avg, short_avg
        dt = dates_utc[i].to_pydatetime()
        lp = float(open_df.iloc[i][long_sym]) - slippage
        sp = float(open_df.iloc[i][short_sym]) + slippage
        lcomm = lp * long_vol * commission_rate + lp * long_vol * 0.001  # 多头平仓=卖出，含印花税
        scomm = sp * short_vol * commission_rate
        cash += lp * long_vol - lcomm
        cash -= sp * short_vol + scomm
        trades.append(Trade(dt=dt, direction="long", offset="close", price=lp,
                            volume=long_vol, commission=lcomm,
                            pnl=(lp - long_avg) * long_vol - lcomm, symbol=long_sym))
        trades.append(Trade(dt=dt, direction="short", offset="close", price=sp,
                            volume=short_vol, commission=scomm,
                            pnl=(short_avg - sp) * short_vol - scomm, symbol=short_sym))
        side = 0
        long_sym = short_sym = ""
        long_vol = short_vol = 0
        long_avg = short_avg = 0.0

    for i in range(n):
        # 1) 执行昨日收盘决定的调仓（今日开盘撮合）
        if pending is not None:
            if side != 0:
                _close_pair(i)
            if pending != 0:
                _open_pair(i, pending)
            pending = None

        # 2) 收盘 mark-to-market：现金 + 多头市值 - 空头负债
        mv = 0.0
        if side != 0:
            mv += long_vol * float(close_df.iloc[i][long_sym])
            mv -= short_vol * float(close_df.iloc[i][short_sym])
        equity_vals.append(cash + mv)

        # 3) 收盘算 z，定次日动作
        zi = float(z.iloc[i]) if pd.notna(z.iloc[i]) else None
        if zi is None or i >= n - 1:
            continue
        if side == 0:
            if zi > entry_z:
                pending = -1   # A 强过头 → 空 A 多 B
            elif zi < -entry_z:
                pending = 1
        elif abs(zi) < exit_z:
            pending = 0

    equity = pd.Series(equity_vals, index=dates_utc)
    result = _metrics(equity, trades, init_capital, benchmark_close, benchmark_name)
    result["pair_symbols"] = [sym_a, sym_b]
    result["pair_zscore"] = [
        {"dt": str(d.date()), "value": round(float(v), 3)}
        for d, v in z.items() if pd.notna(v)
    ]
    result["pair_window"] = window
    result["pair_entry_z"] = entry_z
    result["pair_exit_z"] = exit_z
    return result, trades


# ── 主入口 ────────────────────────────────────────────────────────────

def run(job_id: int) -> dict:
    """主入口：从 PG 读 job → 执行回测 → 写结果到 PG。"""
    from app.db.models.backtest import BacktestJob, BacktestTrade
    from app.db.postgres import SyncSessionLocal

    with SyncSessionLocal() as db:
        job: BacktestJob | None = db.get(BacktestJob, job_id)
        if not job:
            raise ValueError(f"BacktestJob {job_id} not found")

        job.status = "running"
        # 在 session 内取出后续要用的字段：commit 后 job 会 detach，
        # 出 with 块再读 ORM 属性会触发 DetachedInstanceError（见 S3）。
        symbol = job.symbol
        start_date = str(job.start_date)
        end_date = str(job.end_date)
        class_name = job.class_name
        params = job.params or {}
        commission_rate = job.commission_rate
        slippage = job.slippage
        init_capital = job.init_capital
        benchmark = job.benchmark or _DEFAULT_BENCHMARK
        db.commit()

    try:
        # 基准：按 job.benchmark lazy 加载并缓存到 ArcticDB，失败返回空 Series 不影响主回测
        benchmark_close = _load_index_close(benchmark, start_date, end_date)

        if class_name == ROTATION_CLASS:
            # 多标的动量轮动：标的列表与轮动参数存 params JSON（零迁移）
            rot = params or {}
            rot_symbols = list(rot.get("symbols") or [])
            if len(rot_symbols) < 2:
                raise RuntimeError("rotation requires at least 2 symbols")
            logger.info("rotation job={} symbols={}", job_id, rot_symbols)
            result, all_trades = run_rotation(
                rot_symbols, start_date, end_date,
                init_capital, commission_rate, slippage,
                lookback=int(rot.get("lookback", 60)),
                rebalance_days=int(rot.get("rebalance_days", 20)),
                benchmark_close=benchmark_close,
                benchmark_name=_benchmark_name(benchmark),
            )
        elif class_name == PAIR_CLASS:
            # 配对交易：A/B 标的与 z-score 参数存 params JSON（零迁移）
            pr = params or {}
            symbol_a, symbol_b = pr.get("symbol_a"), pr.get("symbol_b")
            if not symbol_a or not symbol_b:
                raise RuntimeError("pair trading requires symbol_a and symbol_b")
            logger.info("pair job={} {} vs {}", job_id, symbol_a, symbol_b)
            result, all_trades = run_pair(
                symbol_a, symbol_b, start_date, end_date,
                init_capital, commission_rate, slippage,
                window=int(pr.get("window", 60)),
                entry_z=float(pr.get("entry_z", 2.0)),
                exit_z=float(pr.get("exit_z", 0.5)),
                benchmark_close=benchmark_close,
                benchmark_name=_benchmark_name(benchmark),
            )
        else:
            # 1. 加载 K 线
            bars = _load_bars(symbol, start_date, end_date)
            if len(bars) < 2:
                raise RuntimeError(f"insufficient bars for {symbol}: {len(bars)}")

            logger.info("backtest job={} bars={} symbol={}", job_id, len(bars), symbol)

            # 2-4. 实例化策略 → 逐 bar 撮合 → 算指标（核心提取为 _simulate，复用给扫参）
            result, all_trades = _simulate(
                bars, symbol, class_name, params,
                init_capital, commission_rate, slippage,
                benchmark_close=benchmark_close,
                benchmark_name=_benchmark_name(benchmark),
            )

        # 5. 落库
        with SyncSessionLocal() as db:
            job = db.get(BacktestJob, job_id)
            if job is None:
                raise ValueError(f"BacktestJob {job_id} not found")
            job.status = "done"
            job.result = result
            job.finished_at = datetime.now(tz=UTC)

            for t in all_trades:
                db.add(BacktestTrade(
                    job_id=job_id,
                    symbol=t.symbol or symbol,
                    direction=t.direction,
                    offset=t.offset,
                    price=t.price,
                    volume=t.volume,
                    dt=t.dt,
                    pnl=t.pnl,
                ))
            db.commit()

        logger.info("backtest job={} done: return={:.2%}", job_id, result["total_return"])
        return result

    except Exception as exc:
        logger.exception("backtest job={} failed: {}", job_id, exc)
        with SyncSessionLocal() as db:
            job = db.get(BacktestJob, job_id)
            if job:
                job.status = "failed"
                job.error = str(exc)[:1024]
                job.finished_at = datetime.now(tz=UTC)
                db.commit()
        raise
