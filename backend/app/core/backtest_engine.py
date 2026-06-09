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


# ── 策略类注册表 ──────────────────────────────────────────────────────

STRATEGY_CLASSES: dict[str, type] = {}


def _load_strategy_classes() -> None:
    if STRATEGY_CLASSES:
        return
    from app.strategies.examples.boll import BollStrategy
    from app.strategies.examples.ma_cross import MaCrossStrategy
    from app.strategies.examples.macd import MacdStrategy
    from app.strategies.examples.rsi import RsiStrategy
    from app.strategies.examples.turtle import TurtleStrategy
    STRATEGY_CLASSES["MaCrossStrategy"] = MaCrossStrategy
    STRATEGY_CLASSES["MacdStrategy"] = MacdStrategy
    STRATEGY_CLASSES["RsiStrategy"] = RsiStrategy
    STRATEGY_CLASSES["BollStrategy"] = BollStrategy
    STRATEGY_CLASSES["TurtleStrategy"] = TurtleStrategy


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

_DEFAULT_BENCHMARK = "000300"   # 沪深300
_BENCHMARK_NAME = "沪深300"


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


def _metrics(
    equity: pd.Series,
    trades: list[Trade],
    init_capital: float,
    benchmark_close: pd.Series | None = None,
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
    win_rate = len(wins) / len(closed_pnls) if closed_pnls else 0.0
    losing_pnl = sum(pnl for pnl in closed_pnls if pnl < 0)
    profit_factor = (
        sum(wins) / abs(losing_pnl)
        if losing_pnl < 0 else float("inf")
    )

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
    }
    if benchmark_close is not None and not benchmark_close.empty:
        out.update(_benchmark_metrics(equity, benchmark_close, init_capital))
    return out


def _benchmark_metrics(equity: pd.Series, benchmark_close: pd.Series, init_capital: float) -> dict:
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

    bench_curve = [
        {"dt": str(d.date()), "value": round(float(v), 2)}
        for d, v in zip(bench_norm.index, bench_norm.values, strict=False)
    ]
    return {
        "benchmark": _BENCHMARK_NAME,
        "benchmark_return": round(bench_return, 4),
        "excess_return": round(total_return - bench_return, 4),
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        "information_ratio": round(information_ratio, 4),
        "benchmark_curve": bench_curve,
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
    result = _metrics(equity, all_trades, init_capital, benchmark_close)
    return result, all_trades


_SWEEP_METRIC_KEYS = (
    "total_return",
    "annual_return",
    "sharpe",
    "max_drawdown",
    "win_rate",
    "trade_count",
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
        db.commit()

    try:
        # 1. 加载 K 线
        bars = _load_bars(symbol, start_date, end_date)
        if len(bars) < 2:
            raise RuntimeError(f"insufficient bars for {symbol}: {len(bars)}")

        logger.info("backtest job={} bars={} symbol={}", job_id, len(bars), symbol)

        # 基准（沪深300）：lazy 加载并缓存到 ArcticDB，失败返回空 Series 不影响主回测
        benchmark_close = _load_index_close(_DEFAULT_BENCHMARK, start_date, end_date)

        # 2-4. 实例化策略 → 逐 bar 撮合 → 算指标（核心提取为 _simulate，复用给扫参）
        result, all_trades = _simulate(
            bars, symbol, class_name, params,
            init_capital, commission_rate, slippage,
            benchmark_close=benchmark_close,
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
                    symbol=symbol,
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
