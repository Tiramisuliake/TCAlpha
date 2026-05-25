"""行情业务逻辑（Phase 1 实现）。"""


async def query_kline(symbol: str, period: str, limit: int) -> list[dict]:
    # TODO Phase 1: 优先查 Redis 缓存 → 查 ArcticDB → 若无则触发 Celery 下载
    return []
