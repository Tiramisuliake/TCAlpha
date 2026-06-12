"""回测报告导出（services/report.py）单元测试。"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.report import build_backtest_report


def _job(**overrides) -> SimpleNamespace:
    result = {
        "total_return": 0.1523,
        "annual_return": 0.21,
        "sharpe": 1.234,
        "max_drawdown": -0.082,
        "win_rate": 0.6,
        "trade_count": 12,
        "profit_factor": 2.1,
        "final_equity": 1_152_300.0,
        "equity_curve": [
            {"dt": f"2025-01-{d:02d}", "value": 1_000_000 + d * 10_000} for d in range(1, 21)
        ],
        "monthly_returns": [
            {"month": "2025-01", "value": 0.05},
            {"month": "2025-02", "value": -0.02},
        ],
        "benchmark": "沪深300",
        "benchmark_return": 0.04,
        "excess_return": 0.1123,
        "alpha": 0.08,
        "beta": 0.9,
        "benchmark_curve": [
            {"dt": f"2025-01-{d:02d}", "value": 1_000_000 + d * 3_000} for d in range(1, 21)
        ],
    }
    base = {
        "name": "测试回测",
        "symbol": "sh600000",
        "class_name": "MaCrossStrategy",
        "start_date": "2025-01-01",
        "end_date": "2025-01-20",
        "period": "1d",
        "result": result,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _trade(pnl: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        dt=datetime(2025, 1, 5, tzinfo=UTC),
        symbol="sh600000",
        direction="long",
        offset="open" if pnl is None else "close",
        price=10.5,
        volume=100,
        pnl=pnl,
    )


def test_report_contains_core_sections():
    html = build_backtest_report(_job(), [_trade(), _trade(pnl=120.0)])

    assert "<!DOCTYPE html>" in html
    assert "测试回测" in html
    assert "sh600000" in html
    assert "总收益率" in html and "15.23%" in html
    assert "<svg" in html                      # 资金曲线 SVG
    assert "月度收益" in html and "2025" in html
    assert "成交明细" in html and "买入" in html and "卖出" in html
    assert "基准对比" in html and "超额收益" in html
    assert "不构成投资建议" in html


def test_report_without_optional_blocks():
    """无基准 / 无月度 / 无成交：对应区块不渲染，主体仍完整。"""
    job = _job()
    job.result = {
        "total_return": 0.01,
        "sharpe": 0.5,
        "equity_curve": [
            {"dt": "2025-01-01", "value": 1_000_000},
            {"dt": "2025-01-02", "value": 1_010_000},
        ],
    }
    html = build_backtest_report(job, [])

    assert "基准对比" not in html
    assert "月度收益" not in html
    assert "成交明细" not in html
    assert "<svg" in html
    assert "总收益率" in html


def test_report_escapes_user_content():
    """名称中的 HTML 被转义，防注入。"""
    job = _job(name="<script>alert(1)</script>")
    html = build_backtest_report(job, [])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
