---
name: sqlalchemy-orm
description: SQLAlchemy 2.0 异步 ORM / 模型定义 / 查询 / 关系 / 事务。触发词：SQLAlchemy、ORM、模型、Model、AsyncSession、查询、关系、外键
---

# SQLAlchemy 2.0 异步 ORM

## 基类

`app/db/postgres.py` 定义了 `Base(DeclarativeBase)`，所有模型继承它。

## 模型定义模板（2.0 风格）

```python
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="stopped")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 关系（可选）
    user: Mapped["User"] = relationship(back_populates="strategies", lazy="selectin")
```

**所有模型必须在 `app/db/models/__init__.py` 里 re-export**，否则 Alembic autogenerate 看不到。

## 字段类型对照

| Python | SQLAlchemy | PG 类型 |
|---|---|---|
| `int` | `Integer` | int4 |
| `int`（大） | `BigInteger` | int8 |
| `str` | `String(N)` | varchar(N) |
| `str`（不限） | `Text` | text |
| `float` | `Float` / `Numeric` | float8 / numeric |
| `bool` | `Boolean` | bool |
| `datetime` | `DateTime(timezone=True)` | timestamptz |
| `date` | `Date` | date |
| `dict` / `list` | `JSON` | jsonb |
| `Decimal` | `Numeric(precision, scale)` | numeric |

**时间字段一律 `DateTime(timezone=True)`**。

## 查询（异步）

```python
from sqlalchemy import select, update, delete

# select 单条
stmt = select(StrategyConfig).where(StrategyConfig.id == sid)
row = (await db.execute(stmt)).scalar_one_or_none()

# select 列表
stmt = select(StrategyConfig).where(StrategyConfig.user_id == uid).order_by(StrategyConfig.created_at.desc())
rows = (await db.execute(stmt)).scalars().all()

# update
await db.execute(update(StrategyConfig).where(StrategyConfig.id == sid).values(status="running"))
await db.commit()

# delete
await db.execute(delete(StrategyConfig).where(StrategyConfig.id == sid))
await db.commit()

# insert（推荐 add + commit）
obj = StrategyConfig(user_id=uid, name="ma cross")
db.add(obj)
await db.commit()
await db.refresh(obj)
```

## 关系加载

| 场景 | 用法 |
|---|---|
| 默认 lazy load | `lazy="select"` — async 会报 `MissingGreenlet` |
| **推荐 async** | `lazy="selectin"`（额外一条 IN 查询，避免 N+1） |
| 同关系小数据 | `lazy="joined"`（一次 JOIN） |
| 显式预加载 | `select(X).options(selectinload(X.children))` |

## 事务

```python
async with db.begin():   # 自动 commit / rollback
    db.add(obj1)
    db.add(obj2)
```

或手动 `await db.commit() / db.rollback()`。

## 性能要点

- `select(Model.id, Model.name)` 只取字段，避免拉全行
- 批量插入用 `db.add_all([...])`
- 批量更新用 `update().where(...).values(...)`
- N+1 → 加 `selectinload` / `joinedload`

## 禁止

- ❌ 字符串拼 SQL（注入风险）：`db.execute(text(f"select * from x where id={id}"))`
- ❌ 在 async 上下文里用同步 session
- ❌ 跨 request 复用 session（必须 `Depends(get_db)`）
- ❌ 忘记 `await db.commit()`（默认不自动提交）

## raw SQL（确实需要时）

```python
from sqlalchemy import text
stmt = text("SELECT id, name FROM x WHERE created_at > :ts").bindparams(ts=cutoff)
rows = (await db.execute(stmt)).mappings().all()
```

**永远绑定参数，不要字符串拼接。**
