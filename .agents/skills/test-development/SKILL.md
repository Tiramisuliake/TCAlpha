---
name: test-development
description: pytest / pytest-asyncio / FastAPI TestClient / 后端测试策略。触发词：测试、pytest、test、单元测试、集成测试、TDD、mock、fixture
---

# 测试开发

## 目录

```
backend/tests/
├── conftest.py        共享 fixture（client、test DB）
├── test_health.py     冒烟
├── test_market.py     /api/market 接口
├── test_services_*    service 单元测试
└── test_strategies_*  策略测试
```

## 运行

```bash
make test                      # 全跑
uv run pytest tests/test_x.py  # 单文件
uv run pytest -k "ma_cross"    # 关键词过滤
uv run pytest -x -v            # 第一个失败就停 + 详细
uv run pytest --cov=app        # 覆盖率
```

## FastAPI TestClient 模板

```python
def test_create_strategy(client):
    r = client.post("/api/strategy/", json={
        "name": "test",
        "class_name": "MaCrossStrategy",
        "symbol": "sh600000",
        "params": {"fast": 5, "slow": 20},
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "test"
    assert body["symbol"] == "sh600000"
```

## 异步测试

`pyproject.toml` 已配 `asyncio_mode = "auto"`，直接用 `async def`：

```python
import pytest

async def test_service_async():
    result = await some_service.do()
    assert result.ok
```

## DB 测试策略

```python
# conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.db.postgres import Base

TEST_URL = "postgresql+asyncpg://tcalpha:dev@localhost:5432/tcalpha_test"

@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db(test_engine):
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as s:
        yield s
        await s.rollback()
```

或更激进：用事务回滚隔离每个用例。

## Mock 外部依赖

```python
from unittest.mock import patch, AsyncMock

@patch("app.services.data.ak.stock_zh_a_hist")
def test_download(mock_ak):
    mock_ak.return_value = make_fake_df()
    result = download_one_symbol("sh600000")
    assert result["ok"]
```

AKShare / OpenAI 这种外部 API 必须 mock，不能让 CI 真请求。

## 策略测试模板

```python
def test_ma_cross_signal():
    from app.strategies.examples.ma_cross import MaCrossStrategy

    s = MaCrossStrategy("sh600000", params={"fast": 3, "slow": 5})
    bars = make_fake_bars([10, 11, 12, 13, 14, 15, 16, 17])
    for b in bars:
        s.on_bar(b)
    assert s.state.fast_ma > 0
```

## 覆盖率目标（个人版宽松）

| 模块 | 目标 |
|---|---|
| utils / symbol / period | 90%+ |
| services | 70%+ |
| api 路由 | 60%+（冒烟为主） |
| strategies | 80%+ |
| Celery 任务 | 50%（mock 多） |

## 禁止

- ❌ 测试里 `time.sleep(2)` 等异步完成（用 mock）
- ❌ 一个测试函数测 10 个断言
- ❌ 共用一个 DB 不清理
- ❌ 把生产 .env 复用到测试

## TDD 节奏（推荐复杂逻辑）

1. 红：先写失败的测试
2. 绿：写最小代码让测试过
3. 重构：在测试保护下清理

回测引擎 / 撮合 / 信号生成 这类核心逻辑强烈建议 TDD。
