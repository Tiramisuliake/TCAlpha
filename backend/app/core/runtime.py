"""策略运行时（Phase 4）。

流程：
  1. 从 ArcticDB 加载历史 K 线热身 ArrayManager
  2. 循环：
     a. match() 撮合上一轮信号的挂单
     b. 拉取最新 bar（AKShare 实时 or 最新日 K）
     c. strategy.on_bar(bar)
     d. 检查 _pending_signal → SimGateway.send_order()
     e. 发布 signal 到 Redis
  3. 检测 Redis stop 标志 → 退出
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from loguru import logger

from app.core.backtest_engine import _load_bars, get_strategy_class
from app.core.pubsub import publish_signal, running_key, stop_key
from app.core.pubsub import get_sync_redis
from app.core.sim_gateway import SimGateway
from app.db.models.strategy import StrategyConfig
from app.db.postgres import SyncSessionLocal

# 热身所需历史 bar 数量
_WARMUP_BARS = 120
# 两次 bar 拉取间隔（秒）— 开发期用日 K 模式时此值不影响
_POLL_INTERVAL = 60


class StrategyRuntime:
    def __init__(self, strategy_id: int) -> None:
        self.strategy_id = strategy_id

    def run(self, celery_task_id: str) -> dict:
        """主循环，供 Celery task 调用。阻塞直到 stop 或异常。"""
        r = get_sync_redis()

        # 1. 从 PG 加载策略配置
        with SyncSessionLocal() as db:
            cfg: StrategyConfig | None = db.get(StrategyConfig, self.strategy_id)
            if not cfg:
                raise ValueError(f"StrategyConfig {self.strategy_id} not found")
            user_id = cfg.user_id
            symbol = cfg.symbol
            class_name = cfg.class_name
            params = cfg.params or {}

        # 标记运行中
        r.set(running_key(self.strategy_id), celery_task_id, ex=86400)

        # 2. 实例化策略
        cls = get_strategy_class(class_name)
        strategy = cls(symbol, params)
        strategy.state.pos = 0

        gw = SimGateway(user_id=user_id, strategy_id=self.strategy_id)

        # 3. 热身：从 ArcticDB 加载历史 bars
        from datetime import timedelta
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=365)
        bars = _load_bars(symbol, str(start.date()), str(end.date()))
        warmup_bars = bars[-_WARMUP_BARS:] if len(bars) >= _WARMUP_BARS else bars

        for bar in warmup_bars:
            strategy.on_bar(bar)
            strategy._pending_signal = None  # 热身期不下单

        logger.info(
            "StrategyRuntime: strategy={} symbol={} warmed up with {} bars",
            self.strategy_id, symbol, len(warmup_bars),
        )

        # 4. 主循环 — 用最新日 K 驱动（Phase 4 简化版；Phase 5 接 AKShare 实时分钟 K）
        tick_count = 0
        last_bar_dt = bars[-1].datetime if bars else None

        while True:
            # 检查停止标志
            if r.exists(stop_key(self.strategy_id)):
                logger.info("StrategyRuntime: stop signal received for strategy={}", self.strategy_id)
                r.delete(stop_key(self.strategy_id))
                break

            # 拉取最新 bar（每轮拉一次，判断是否有新 K 线）
            fresh_bars = _load_bars(symbol, str(start.date()), str(end.date()))
            if fresh_bars and (last_bar_dt is None or fresh_bars[-1].datetime > last_bar_dt):
                new_bars = [b for b in fresh_bars if last_bar_dt is None or b.datetime > last_bar_dt]
                for bar in new_bars:
                    # 撮合上一轮挂单
                    gw.match(bar)
                    strategy.state.pos = gw.get_position(symbol)

                    # 策略计算
                    strategy.on_bar(bar)

                    # 处理信号
                    sig = getattr(strategy, "_pending_signal", None)
                    if sig:
                        direction, offset, volume = sig
                        order_id = gw.send_order(symbol, direction, offset, bar.close_price, volume)
                        strategy._pending_signal = None
                        logger.info(
                            "StrategyRuntime: signal {} {} vol={} → order={}",
                            direction, offset, volume, order_id,
                        )

                    # 发布信号状态到 Redis
                    publish_signal(
                        self.strategy_id,
                        {
                            "strategy_id": self.strategy_id,
                            "symbol": symbol,
                            "bar_dt": str(bar.datetime.date()),
                            "direction": strategy.vars.direction,
                            "strength": strategy.vars.strength,
                            "tip": strategy.vars.tip,
                            "pos": strategy.state.pos,
                            "ts": datetime.now(tz=timezone.utc).isoformat(),
                        },
                    )
                    last_bar_dt = bar.datetime
                    tick_count += 1

            # 更新 running_key TTL 心跳
            r.expire(running_key(self.strategy_id), 86400)

            time.sleep(_POLL_INTERVAL)

        # 清理
        r.delete(running_key(self.strategy_id))

        # 更新 DB 状态
        with SyncSessionLocal() as db:
            cfg = db.get(StrategyConfig, self.strategy_id)
            if cfg:
                cfg.status = "stopped"
                db.commit()

        return {"strategy_id": self.strategy_id, "ticks": tick_count, "status": "stopped"}
