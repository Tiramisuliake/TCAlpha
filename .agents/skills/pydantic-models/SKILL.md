---
name: pydantic-models
description: Pydantic v2 / BaseModel / Field / 验证器 / DTO / Settings / 三层策略模型。触发词：Pydantic、BaseModel、Field、DTO、Schema、序列化、validate_assignment、配置
---

# Pydantic v2

## 三类用途

| 用途 | 位置 |
|---|---|
| 配置 | `app/config.py` 继承 `BaseSettings` |
| API DTO | `app/schemas/*.py` 继承 `BaseModel` |
| 策略 Params/State/Vars | `app/strategies/base.py` 三层基类 |

## BaseModel 模板

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrategyCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,       # 自动 strip 字符串
        validate_assignment=True,        # 赋值时校验
    )

    name: str = Field(min_length=1, max_length=128)
    class_name: str
    symbol: str = Field(pattern=r"^(sh|sz|bj)\d{6}$")
    params: dict[str, object] = Field(default_factory=dict)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        from app.utils.symbol import normalize
        return normalize(v)


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # 允许从 ORM 实例构造

    id: int
    name: str
    class_name: str
    symbol: str
    params: dict[str, object]
    created_at: datetime
```

## Settings 模板

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    database_url: str
    redis_url: str
```

## 三层策略模型（沿用观澜）

```python
from pydantic import BaseModel, ConfigDict, Field

class BaseParams(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

class BaseState(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    pos: int = Field(default=0, title="持仓")

class BaseVars(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    direction: int = Field(default=0, title="方向", description="1 多 / -1 空 / 0 中性")
    strength: int = Field(default=0, ge=0, le=100, title="强度")
    tip: str = Field(default="", title="提示")
    suggest_price: float = Field(default=0.0, title="建议价")
    allow_open_long: bool = Field(default=False, title="允许开多")
    allow_open_short: bool = Field(default=False, title="允许开空")
```

策略子类只需 extend：

```python
class MacdParams(BaseParams):
    fast: int = Field(default=12, ge=2, le=100, title="快线周期")
    slow: int = Field(default=26, ge=5, le=200, title="慢线周期")
```

`title` 字段后期前端可读取生成动态表单。

## v1 → v2 速查（避免误用）

| v1 | v2 |
|---|---|
| `class Config: orm_mode = True` | `model_config = ConfigDict(from_attributes=True)` |
| `@validator` | `@field_validator` |
| `@root_validator` | `@model_validator(mode="after")` |
| `.dict()` | `.model_dump()` |
| `.json()` | `.model_dump_json()` |
| `parse_obj` | `model_validate` |
| `Config.fields = ...` | `Field(...)` 直接写在字段上 |

## 序列化注意

- ORM 对象 → DTO：`StrategyOut.model_validate(obj)`（需 `from_attributes=True`）
- `datetime` 默认 ISO 字符串
- `Decimal` 默认字符串（避免精度丢失）；要数值用 `model_config = ConfigDict(...)` + `json_encoders` 自定义

## 验证错误

FastAPI 自动把 ValidationError → 422 响应。手动场景：

```python
from pydantic import ValidationError
try:
    obj = MyModel(**raw)
except ValidationError as e:
    logger.error(e.errors())
```

## 禁止

- ❌ Pydantic 模型里写业务逻辑（应在 service 层）
- ❌ 用 `Any` 兜底（用 `object` 或精确联合类型）
- ❌ 序列化敏感字段（密码 hash 必须从 `*Out` 类型排除）
