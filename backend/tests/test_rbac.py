"""RBAC 权限闸门测试（Phase 7 v0.7.1）。

策略：用 FastAPI `dependency_overrides` 把 `get_current_user` 替换为构造的
AuthUser，避免依赖真 DB / JWT 签发；只断言路由权限闸门 401/403 行为。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth_deps import AuthUser, get_current_user
from app.main import app

# ── 三种角色的 AuthUser（与种子迁移保持一致）────────────────────────

ADMIN = AuthUser(
    id=1,
    username="admin",
    display_name="Admin",
    is_super=True,
    role_codes=frozenset({"admin"}),
    permission_codes=frozenset(),  # super 绕过，留空也行
    data_scope="all",
)

TRADER_PERMS = frozenset({
    "strategy.read", "strategy.write", "strategy.delete", "strategy.run",
    "sim.order.read", "sim.order.cancel",
    "backtest.read", "backtest.run",
    "data.read", "data.download",
    "ai.chat", "ai.watch",
    "notify.rule.read", "notify.rule.write",
})
TRADER = AuthUser(
    id=2,
    username="trader",
    display_name="Trader",
    is_super=False,
    role_codes=frozenset({"trader"}),
    permission_codes=TRADER_PERMS,
    data_scope="self",
)

VIEWER_PERMS = frozenset({
    "strategy.read", "sim.order.read", "backtest.read",
    "data.read", "ai.chat", "notify.rule.read",
})
VIEWER = AuthUser(
    id=3,
    username="viewer",
    display_name="Viewer",
    is_super=False,
    role_codes=frozenset({"viewer"}),
    permission_codes=VIEWER_PERMS,
    data_scope="self",
)


@pytest.fixture(autouse=True)
def _ensure_engine():
    """TestClient 不会跑 lifespan，需要手动 init_engine 才能拿到 get_db session。"""
    import app.db.postgres as pg

    if pg.async_session_factory is None:
        pg.init_engine()
    yield


@pytest.fixture
def as_user():
    """临时把 get_current_user + get_current_user_id override 成指定 user，yield 后清掉。

    get_current_user_id 也要 override：硬切 401 后它不再 fallback，测试不带真实
    token，需让它返回 override 用户的 id，成功路径才能走到数据过滤逻辑。
    """
    from app.deps import get_current_user_id

    def _setter(user: AuthUser | None) -> None:
        if user is None:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_id, None)
        else:
            app.dependency_overrides[get_current_user] = lambda: user
            app.dependency_overrides[get_current_user_id] = lambda: user.id

    yield _setter
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_id, None)


@pytest.fixture
def rbac_client() -> TestClient:
    return TestClient(app)


# ── 401：无 token ────────────────────────────────────────────────


def test_no_token_returns_401(rbac_client):
    r = rbac_client.get("/api/notify/event-types")
    assert r.status_code == 401


def test_no_token_blocks_strategy_list(rbac_client):
    r = rbac_client.get("/api/strategy/list")
    assert r.status_code == 401


# ── admin / super 全通 ──────────────────────────────────────────


def test_admin_reads_notify(rbac_client, as_user):
    as_user(ADMIN)
    r = rbac_client.get("/api/notify/event-types")
    assert r.status_code == 200
    assert "event_types" in r.json()


def test_super_bypasses_with_empty_perms(rbac_client, as_user):
    """super=True 即使 permission_codes 为空也能过任何闸门。"""
    as_user(ADMIN)
    r = rbac_client.get("/api/notify/event-types")
    assert r.status_code == 200


# ── viewer：可读不可写 ─────────────────────────────────────────


def test_viewer_reads_notify(rbac_client, as_user):
    as_user(VIEWER)
    r = rbac_client.get("/api/notify/event-types")
    assert r.status_code == 200


def test_viewer_cannot_write_notify(rbac_client, as_user):
    as_user(VIEWER)
    r = rbac_client.post(
        "/api/notify/test",
        json={"content": "x", "feishu_webhook": "https://example.com/x"},
    )
    assert r.status_code == 403
    assert "notify.rule.write" in r.json()["detail"]


def test_viewer_cannot_delete_strategy(rbac_client, as_user):
    as_user(VIEWER)
    r = rbac_client.delete("/api/strategy/123")
    assert r.status_code == 403
    assert "strategy.delete" in r.json()["detail"]


def test_viewer_cannot_run_backtest(rbac_client, as_user):
    as_user(VIEWER)
    r = rbac_client.post(
        "/api/backtest/submit",
        json={
            "name": "x", "class_name": "Ma", "symbol": "sh600000",
            "params": {}, "start_date": "2025-01-01", "end_date": "2025-01-31",
            "init_capital": 100000, "commission_rate": 0.0003, "slippage": 0.0,
        },
    )
    assert r.status_code == 403
    assert "backtest.run" in r.json()["detail"]


def test_viewer_cannot_download_data(rbac_client, as_user):
    as_user(VIEWER)
    r = rbac_client.post("/api/data/download?symbol=sh600000&period=1d")
    assert r.status_code == 403
    assert "data.download" in r.json()["detail"]


# ── trader：操作类全通，系统管理不通 ───────────────────────────


def test_trader_can_delete_strategy(rbac_client, as_user):
    """trader 应该有 strategy.delete；404 是业务层语义，闸门通过。"""
    as_user(TRADER)
    r = rbac_client.delete("/api/strategy/999999")
    assert r.status_code != 403  # 闸门通过；可能 401/404/500，但绝非 403


def test_trader_can_write_notify_rules(rbac_client, as_user):
    as_user(TRADER)
    # webhook 缺失会 400，闸门通过的关键是 != 403
    r = rbac_client.post(
        "/api/notify/test",
        json={"content": "ping", "feishu_webhook": ""},
    )
    assert r.status_code != 403


def test_trader_can_download_data(rbac_client, as_user):
    """trader 应该有 data.download 权限。"""
    as_user(TRADER)
    r = rbac_client.post("/api/data/download?symbol=sh600000&period=1d")
    # 端点目前是占位（不查 DB / 不入队），只验闸门通过
    assert r.status_code != 403
    assert r.status_code == 200
