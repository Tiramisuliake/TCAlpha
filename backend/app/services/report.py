"""回测报告导出（自包含 HTML，零外部依赖）。

不引 Jinja2 / 不依赖 CDN：指标表纯 HTML，资金曲线 / 回撤用内联 SVG，
月度收益用上色表格 —— 导出文件离线可看、可存档、可分享。
"""
from __future__ import annotations

from html import escape
from typing import Any

from app.utils.trading_period import now_cn

_W, _H = 860, 260  # SVG 画布

_METRIC_ROWS: list[tuple[str, str, str]] = [
    # (result key, 标签, 格式: pct/num/int/money)
    ("total_return", "总收益率", "pct"),
    ("annual_return", "年化收益", "pct"),
    ("sharpe", "夏普比率", "num"),
    ("sortino", "Sortino", "num"),
    ("max_drawdown", "最大回撤", "pct"),
    ("calmar", "Calmar", "num"),
    ("volatility", "年化波动率", "pct"),
    ("win_rate", "胜率", "pct"),
    ("profit_factor", "盈亏比", "num"),
    ("trade_count", "交易次数", "int"),
    ("expectancy", "单笔期望(元)", "money"),
    ("avg_holding_days", "平均持仓(天)", "num"),
    ("final_equity", "期末资金", "money"),
]

_BENCH_ROWS: list[tuple[str, str, str]] = [
    ("benchmark_return", "基准收益", "pct"),
    ("excess_return", "超额收益", "pct"),
    ("alpha", "Alpha(年化)", "pct"),
    ("beta", "Beta", "num"),
    ("information_ratio", "信息比率", "num"),
]


def _fmt(v: Any, kind: str) -> str:
    if v is None:
        return "-"
    try:
        if kind == "pct":
            return f"{float(v) * 100:.2f}%"
        if kind == "int":
            return f"{int(v)}"
        if kind == "money":
            return f"{float(v):,.2f}"
        return f"{float(v):.3f}"
    except (TypeError, ValueError):
        return escape(str(v))


def _scale(values: list[float], lo: float, hi: float, size: int, invert: bool = False) -> list[float]:
    span = (hi - lo) or 1.0
    out = []
    for v in values:
        r = (v - lo) / span
        out.append(round((1 - r) * size if not invert else r * size, 2))
    return out


def _polyline(xs: list[float], ys: list[float]) -> str:
    return " ".join(f"{x},{y}" for x, y in zip(xs, ys, strict=False))


def _svg_equity(curve: list[dict], bench: list[dict] | None) -> str:
    """资金曲线（蓝）+ 基准（灰虚线）+ 回撤面积（红，下半区）内联 SVG。"""
    if len(curve) < 2:
        return "<p>（资金曲线数据不足）</p>"
    vals = [float(p["value"]) for p in curve]
    dts = [str(p["dt"])[:10] for p in curve]
    n = len(vals)
    xs = [round(i * _W / (n - 1), 2) for i in range(n)]

    # 主区（0~170）：资金 + 基准；副区（185~255）：回撤
    bench_vals: list[float] = []
    if bench:
        by_day = {str(p["dt"])[:10]: float(p["value"]) for p in bench}
        bench_vals = [by_day.get(d, float("nan")) for d in dts]
        bench_vals = [v for v in bench_vals]  # 保留 NaN 占位
    all_vals = vals + [v for v in bench_vals if v == v]
    lo, hi = min(all_vals), max(all_vals)
    ys = [round(10 + y, 2) for y in _scale(vals, lo, hi, 160)]
    main = f'<polyline fill="none" stroke="#3b82f6" stroke-width="2" points="{_polyline(xs, ys)}"/>'

    bench_line = ""
    if bench_vals and any(v == v for v in bench_vals):
        pts = [
            (x, round(10 + y, 2))
            for x, y, v in zip(xs, _scale([v if v == v else lo for v in bench_vals], lo, hi, 160), bench_vals, strict=False)
            if v == v
        ]
        bench_line = (
            f'<polyline fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="5,4" '
            f'points="{" ".join(f"{x},{y}" for x, y in pts)}"/>'
        )

    # 回撤
    peak = vals[0]
    dd = []
    for v in vals:
        peak = max(peak, v)
        dd.append((v / peak - 1) if peak > 0 else 0.0)
    dd_lo = min(dd) or -1e-9
    dd_ys = [round(185 + y, 2) for y in _scale(dd, dd_lo, 0.0, 70, invert=True)]
    dd_area = (
        f'<polygon fill="rgba(239,68,68,0.25)" stroke="#ef4444" stroke-width="1" '
        f'points="0,185 {_polyline(xs, dd_ys)} {_W},185"/>'
    )

    labels = (
        f'<text x="0" y="{_H - 2}" font-size="10" fill="#64748b">{escape(dts[0])}</text>'
        f'<text x="{_W // 2 - 30}" y="{_H - 2}" font-size="10" fill="#64748b">{escape(dts[n // 2])}</text>'
        f'<text x="{_W - 70}" y="{_H - 2}" font-size="10" fill="#64748b">{escape(dts[-1])}</text>'
        f'<text x="4" y="20" font-size="10" fill="#3b82f6">资金曲线</text>'
        f'<text x="4" y="196" font-size="10" fill="#ef4444">回撤</text>'
    )
    return (
        f'<svg viewBox="0 0 {_W} {_H}" width="100%" xmlns="http://www.w3.org/2000/svg">'
        f"{dd_area}{bench_line}{main}{labels}</svg>"
    )


def _monthly_table(monthly: list[dict]) -> str:
    """年 × 月上色表格（红涨绿跌，A 股惯例）。"""
    if not monthly:
        return ""
    by_year: dict[str, dict[int, float]] = {}
    for m in monthly:
        y, mo = m["month"][:4], int(m["month"][5:7])
        by_year.setdefault(y, {})[mo] = float(m["value"])
    head = "".join(f"<th>{i}月</th>" for i in range(1, 13))
    rows = []
    for y in sorted(by_year):
        cells = []
        for i in range(1, 13):
            v = by_year[y].get(i)
            if v is None:
                cells.append("<td>-</td>")
            else:
                alpha = min(abs(v) * 8, 0.85)
                bg = f"rgba(239,68,68,{alpha:.2f})" if v >= 0 else f"rgba(16,185,129,{alpha:.2f})"
                cells.append(f'<td style="background:{bg}">{v * 100:.1f}%</td>')
        rows.append(f"<tr><th>{escape(y)}</th>{''.join(cells)}</tr>")
    return (
        "<h2>月度收益</h2>"
        f'<table class="grid"><tr><th></th>{head}</tr>{"".join(rows)}</table>'
    )


def _trades_table(trades: list[Any], limit: int = 200) -> str:
    if not trades:
        return ""
    rows = []
    for t in trades[:limit]:
        action = (
            "买入" if (t.offset == "open" and t.direction == "long")
            else "卖空" if t.offset == "open"
            else "卖出" if t.direction == "long"
            else "买回"
        )
        pnl = f"{t.pnl:,.2f}" if t.pnl is not None else "-"
        pnl_cls = "" if t.pnl is None else ("up" if t.pnl >= 0 else "down")
        rows.append(
            f"<tr><td>{escape(str(t.dt)[:10])}</td><td>{escape(t.symbol)}</td>"
            f"<td>{action}</td><td>{t.price:.2f}</td><td>{t.volume}</td>"
            f'<td class="{pnl_cls}">{pnl}</td></tr>'
        )
    more = f"<p class='muted'>（共 {len(trades)} 笔，仅展示前 {limit} 笔）</p>" if len(trades) > limit else ""
    return (
        "<h2>成交明细</h2>"
        '<table class="grid"><tr><th>日期</th><th>标的</th><th>动作</th>'
        f"<th>价格</th><th>数量</th><th>盈亏</th></tr>{''.join(rows)}</table>{more}"
    )


_PORTFOLIO_ROWS: list[tuple[str, str, str]] = [
    ("total_return", "总收益率", "pct"),
    ("annual_return", "年化收益", "pct"),
    ("sharpe", "夏普比率", "num"),
    ("max_drawdown", "最大回撤", "pct"),
    ("win_rate", "调仓胜率", "pct"),
    ("excess_return", "对基准超额", "pct"),
    ("rebalance_count", "调仓次数", "int"),
    ("top_n", "持仓数", "int"),
]


def build_portfolio_report(config: dict, result: dict) -> str:
    """渲染多因子组合回测的自包含 HTML 报告（因子权重 + 指标 + 组合/基准净值 SVG）。"""
    from app.services.factors import FACTORS

    r: dict = result or {}
    weights = config.get("weights") or {}
    w_cells = "".join(
        f'<div class="metric"><div class="label">{escape(FACTORS[k][0] if k in FACTORS else k)}</div>'
        f'<div class="value">{float(v):.1f}</div></div>'
        for k, v in weights.items()
        if v
    ) or '<p class="muted">（无启用因子）</p>'

    metric_cells = "".join(
        f'<div class="metric"><div class="label">{escape(label)}</div>'
        f'<div class="value">{_fmt(r.get(key), kind)}</div></div>'
        for key, label, kind in _PORTFOLIO_ROWS
        if key in r
    )

    top_n = r.get("top_n") or config.get("top_n") or "-"
    rebal = config.get("rebalance_days") or "-"
    lookback = config.get("lookback") or "-"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>TCAlpha 组合回测报告</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 920px;
         margin: 24px auto; padding: 0 16px; color: #1e293b; }}
  h1 {{ font-size: 22px; }} h2 {{ font-size: 16px; margin-top: 28px; }}
  .muted {{ color: #64748b; font-size: 12px; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .metric {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 14px; min-width: 110px; }}
  .metric .label {{ font-size: 11px; color: #64748b; }}
  .metric .value {{ font-size: 16px; font-weight: 600; }}
  .up {{ color: #ef4444; }} .down {{ color: #10b981; }}
</style></head><body>
<h1>TCAlpha 多因子组合回测报告</h1>
<p class="muted">持仓 top {escape(str(top_n))} ｜ 调仓 {escape(str(rebal))} 日 ｜ 回看 {escape(str(lookback))} 日
 ｜ 生成于 {now_cn().strftime("%Y-%m-%d %H:%M")}</p>
<h2>因子权重</h2>
<div class="metrics">{w_cells}</div>
<h2>核心指标</h2>
<div class="metrics">{metric_cells}</div>
<h2>组合净值 vs 全市场等权</h2>
{_svg_equity(r.get("equity_curve") or [], r.get("benchmark_curve"))}
<p class="muted">本报告由 TCAlpha 自动生成，仅供研究复盘，不构成投资建议。</p>
</body></html>"""
    return html


def build_backtest_report(job: Any, trades: list[Any] | None = None) -> str:
    """渲染单个回测 Job 的自包含 HTML 报告。

    job 只需具备 name/symbol/class_name/start_date/end_date/period/result 属性
    （ORM 实例或测试替身均可）；result 为引擎落库的指标 JSON。
    """
    r: dict = job.result or {}
    period = getattr(job, "period", None) or r.get("period") or "1d"

    def _rows(spec: list[tuple[str, str, str]]) -> str:
        cells = []
        for key, label, kind in spec:
            if key not in r:
                continue
            cells.append(
                f'<div class="metric"><div class="label">{escape(label)}</div>'
                f'<div class="value">{_fmt(r.get(key), kind)}</div></div>'
            )
        return "".join(cells)

    bench_block = ""
    if r.get("benchmark"):
        bench_block = (
            f"<h2>基准对比（{escape(str(r['benchmark']))}）</h2>"
            f'<div class="metrics">{_rows(_BENCH_ROWS)}</div>'
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>TCAlpha 回测报告 — {escape(job.name)}</title>
<style>
  body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 920px;
         margin: 24px auto; padding: 0 16px; color: #1e293b; }}
  h1 {{ font-size: 22px; }} h2 {{ font-size: 16px; margin-top: 28px; }}
  .muted {{ color: #64748b; font-size: 12px; }}
  .metrics {{ display: flex; flex-wrap: wrap; gap: 8px; }}
  .metric {{ border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 14px; min-width: 110px; }}
  .metric .label {{ font-size: 11px; color: #64748b; }}
  .metric .value {{ font-size: 16px; font-weight: 600; }}
  table.grid {{ border-collapse: collapse; font-size: 12px; width: 100%; }}
  table.grid th, table.grid td {{ border: 1px solid #e2e8f0; padding: 4px 8px; text-align: right; }}
  table.grid th {{ background: #f8fafc; }}
  .up {{ color: #ef4444; }} .down {{ color: #10b981; }}
</style></head><body>
<h1>TCAlpha 回测报告 — {escape(job.name)}</h1>
<p class="muted">标的 {escape(job.symbol)} ｜ 策略 {escape(job.class_name)} ｜ 周期 {escape(period)}
 ｜ 区间 {escape(str(job.start_date))} ~ {escape(str(job.end_date))}
 ｜ 生成于 {now_cn().strftime("%Y-%m-%d %H:%M")}</p>
<h2>核心指标</h2>
<div class="metrics">{_rows(_METRIC_ROWS)}</div>
{bench_block}
<h2>资金曲线 + 回撤</h2>
{_svg_equity(r.get("equity_curve") or [], r.get("benchmark_curve"))}
{_monthly_table(r.get("monthly_returns") or [])}
{_trades_table(trades or [])}
<p class="muted">本报告由 TCAlpha 自动生成，仅供研究复盘，不构成投资建议。</p>
</body></html>"""
    return html
