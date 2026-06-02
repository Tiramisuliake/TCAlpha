"""离线 seed 一批热门 A 股到 PG `symbols` 表（不依赖 AKShare / Celery）。

用途：dev 联调早期跑这个，前端 K 线 / 策略 / 回测 / 模拟交易等页面立刻能
搜索 / 下拉到候选股票；真要全市场再走 `POST /api/market/symbols/refresh`
走 AKShare 拉 5000+。

数据来源：手工挑选的 50 只 A 股（沪深主板 + 创业板 + 科创板代表），覆盖
银行 / 白酒 / 新能源 / 半导体 / 医药 / 互联网 / 工业 / 消费 等行业。

用法：
    uv --directory backend run python scripts/seed_symbols.py
    # 或 PyCharm 直接 Run
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db.models.symbol import Symbol  # noqa: E402
from app.db.postgres import SyncSessionLocal  # noqa: E402

# (symbol, code, exchange, name, industry)
SEED: list[tuple[str, str, str, str, str]] = [
    # ── 沪市主板 ──────────────────────────────────────────────
    ("sh600000", "600000", "SH", "浦发银行", "银行"),
    ("sh600036", "600036", "SH", "招商银行", "银行"),
    ("sh601398", "601398", "SH", "工商银行", "银行"),
    ("sh601318", "601318", "SH", "中国平安", "保险"),
    ("sh601628", "601628", "SH", "中国人寿", "保险"),
    ("sh600519", "600519", "SH", "贵州茅台", "白酒"),
    ("sh600276", "600276", "SH", "恒瑞医药", "医药"),
    ("sh600887", "600887", "SH", "伊利股份", "食品饮料"),
    ("sh601888", "601888", "SH", "中国中免", "免税零售"),
    ("sh600030", "600030", "SH", "中信证券", "证券"),
    ("sh601012", "601012", "SH", "隆基绿能", "光伏"),
    ("sh600028", "600028", "SH", "中国石化", "石化"),
    ("sh601857", "601857", "SH", "中国石油", "石油"),
    ("sh601088", "601088", "SH", "中国神华", "煤炭"),
    ("sh600900", "600900", "SH", "长江电力", "电力"),
    ("sh601728", "601728", "SH", "中国电信", "通信"),
    ("sh600585", "600585", "SH", "海螺水泥", "建材"),
    ("sh601899", "601899", "SH", "紫金矿业", "有色金属"),
    ("sh600104", "600104", "SH", "上汽集团", "汽车"),
    ("sh601238", "601238", "SH", "广汽集团", "汽车"),

    # ── 深市主板 ──────────────────────────────────────────────
    ("sz000001", "000001", "SZ", "平安银行", "银行"),
    ("sz000002", "000002", "SZ", "万科A", "房地产"),
    ("sz000333", "000333", "SZ", "美的集团", "家电"),
    ("sz000651", "000651", "SZ", "格力电器", "家电"),
    ("sz000858", "000858", "SZ", "五粮液", "白酒"),
    ("sz000568", "000568", "SZ", "泸州老窖", "白酒"),
    ("sz000725", "000725", "SZ", "京东方A", "面板"),
    ("sz000063", "000063", "SZ", "中兴通讯", "通信设备"),
    ("sz002594", "002594", "SZ", "比亚迪", "新能源车"),
    ("sz002475", "002475", "SZ", "立讯精密", "电子"),

    # ── 创业板 ────────────────────────────────────────────────
    ("sz300750", "300750", "SZ", "宁德时代", "新能源电池"),
    ("sz300059", "300059", "SZ", "东方财富", "互联网金融"),
    ("sz300760", "300760", "SZ", "迈瑞医疗", "医疗器械"),
    ("sz300015", "300015", "SZ", "爱尔眼科", "医疗服务"),
    ("sz300124", "300124", "SZ", "汇川技术", "工业控制"),
    ("sz300274", "300274", "SZ", "阳光电源", "光伏逆变器"),
    ("sz300433", "300433", "SZ", "蓝思科技", "电子"),

    # ── 科创板 ────────────────────────────────────────────────
    ("sh688981", "688981", "SH", "中芯国际", "半导体"),
    ("sh688256", "688256", "SH", "寒武纪", "AI 芯片"),
    ("sh688012", "688012", "SH", "中微公司", "半导体设备"),
    ("sh688041", "688041", "SH", "海光信息", "CPU"),
    ("sh688008", "688008", "SH", "澜起科技", "半导体"),
    ("sh688111", "688111", "SH", "金山办公", "软件"),
    ("sh688036", "688036", "SH", "传音控股", "手机"),

    # ── 其他热门 ──────────────────────────────────────────────
    ("sh601658", "601658", "SH", "邮储银行", "银行"),
    ("sh600438", "600438", "SH", "通威股份", "光伏"),
    ("sh603259", "603259", "SH", "药明康德", "医药 CXO"),
    ("sh600690", "600690", "SH", "海尔智家", "家电"),
    ("sz002714", "002714", "SZ", "牧原股份", "养殖"),
    ("sz002352", "002352", "SZ", "顺丰控股", "物流"),
]


def main() -> None:
    inserted = 0
    updated = 0

    with SyncSessionLocal() as db:
        for symbol, code, exchange, name, industry in SEED:
            existing = db.execute(
                select(Symbol).where(Symbol.symbol == symbol)
            ).scalar_one_or_none()
            if existing:
                existing.name = name
                existing.industry = industry
                existing.exchange = exchange
                existing.is_active = True
                updated += 1
            else:
                db.add(
                    Symbol(
                        symbol=symbol,
                        code=code,
                        exchange=exchange,
                        name=name,
                        industry=industry,
                        is_active=True,
                    )
                )
                inserted += 1
        db.commit()

        total = db.execute(select(Symbol).where(Symbol.is_active.is_(True))).scalars().all()
        print(f"[seed] inserted={inserted} updated={updated} total_active={len(total)}")
        print("[seed] 示例（前 5 条）：")
        for s in total[:5]:
            print(f"  {s.symbol:<10}  {s.name:<8}  {s.industry}")


if __name__ == "__main__":
    main()
