---
name: sim-trading
description: 模拟撮合 / SimGateway / 订单状态机 / 持仓管理 / 资金账户。触发词：模拟、SimGateway、模拟交易、撮合、订单、持仓、账户、paper trading
---

# 模拟交易

## 设计目标

- **代码与实盘网关同 interface**（`app/core/gateway.py` Protocol）
- 订单落 PG（`SimOrder` 表），便于审计
- 撮合策略：下一根 bar 开盘价（与回测一致）
- 状态机推进发 Redis 事件给 WebSocket 推送前端

## Gateway 抽象

```python
# app/core/gateway.py
from typing import Protocol

class Gateway(Protocol):
    name: str
    def connect(self) -> None: ...
    def send_order(self, symbol, direction, offset, price, volume) -> str: ...
    def cancel_order(self, order_id: str) -> None: ...
    def subscribe(self, symbol: str) -> None: ...
```

## SimGateway 实现（Phase 4）

```python
# app/core/sim_gateway.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.order import SimOrder

class SimGateway:
    name = "SIM"

    def __init__(self, db_factory, redis):
        self._db_factory = db_factory
        self._redis = redis

    async def send_order(self, user_id, strategy_id, symbol, direction, offset, price, volume) -> int:
        async with self._db_factory() as db:
            o = SimOrder(user_id=user_id, strategy_id=strategy_id,
                         symbol=symbol, direction=direction, offset=offset,
                         price=price, volume=volume, status="submitted")
            db.add(o)
            await db.commit()
            await db.refresh(o)
            await self._publish_status(o)
            return o.id

    async def match(self, next_bar) -> None:
        """收到新 bar 时撮合所有 submitted 订单（按下一 bar 开盘）。"""
        async with self._db_factory() as db:
            stmt = (
                select(SimOrder)
                .where(SimOrder.symbol == next_bar.symbol, SimOrder.status == "submitted")
            )
            orders = (await db.execute(stmt)).scalars().all()
            for o in orders:
                # 涨跌停限制 / 停牌 略
                o.filled_volume = o.volume
                o.status = "filled"
                o.price = next_bar.open_price       # 实际成交价覆盖
            await db.commit()
            for o in orders:
                await self._publish_status(o)

    async def _publish_status(self, o: SimOrder) -> None:
        await self._redis.publish(f"order:user:{o.user_id}", json.dumps({
            "id": o.id, "symbol": o.symbol, "status": o.status,
            "price": o.price, "volume": o.filled_volume,
        }))
```

## 订单状态机

```
submitted → filled
         → partial → filled
         → cancelled
         → rejected
```

不允许 filled / cancelled / rejected 之间互转。

## 持仓管理

不单独建 position 表，而是从 `sim_orders` 实时聚合：

```python
async def get_position(db, user_id: int, symbol: str) -> int:
    stmt = (
        select(SimOrder.direction, SimOrder.offset, func.sum(SimOrder.filled_volume))
        .where(SimOrder.user_id == user_id, SimOrder.symbol == symbol, SimOrder.status == "filled")
        .group_by(SimOrder.direction, SimOrder.offset)
    )
    pos = 0
    for direction, offset, vol in (await db.execute(stmt)):
        sign = 1 if direction == "long" else -1
        sign *= 1 if offset == "open" else -1
        pos += sign * vol
    return pos
```

或缓存到 Redis（`position:{uid}:{symbol}`）。

## 资金账户

简化：
- 用户初始资金存 `users.balance`（或新 `accounts` 表）
- 开仓扣 `price * volume * (1 + commission_rate)`
- 平仓加 `price * volume * (1 - commission_rate - 0.001 if 卖出)`
- 余额不足 → 拒单 `status="rejected"`

## 与策略联动

```python
# Celery 长跑 task 里
async def run_strategy(strategy_id):
    s = await load_strategy(strategy_id)
    gw = SimGateway(...)
    while running:
        bar = await fetch_next_bar(s.symbol)
        await gw.match(bar)          # 撮合上一根遗留订单
        s.on_bar(bar)
        if s.vars.allow_open_long and pos == 0:
            await gw.send_order(uid, sid, s.symbol, "long", "open", bar.close_price, 100)
        elif s.vars.allow_open_short and pos > 0:
            await gw.send_order(uid, sid, s.symbol, "long", "close", bar.close_price, pos)
```

## 前端

订单列表实时刷新：
- WebSocket 订阅 `/ws/orders`
- 后端把 `order:user:{uid}` 转发给该用户的 WS
- 前端 React Query `setQueryData` 更新订单列表

## 升级实盘的预留

未来接 xtquant / qmt 时实现同 Protocol：
- `XtquantGateway` 把 send_order 映射到券商 API
- 业务层（service）不改一行
- 切换：配置 `GATEWAY=sim|xtquant`

## 禁止

- ❌ 撮合用当前 bar 收盘价（未来函数）
- ❌ 不限制 100 股最小单位（A 股规则）
- ❌ 模拟成交 / 实盘成交共用一张表（用 `gateway_type` 字段区分，或拆表）
- ❌ Phase 4 还没做就吹"已支持模拟交易"
