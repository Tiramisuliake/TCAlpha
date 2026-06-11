"""数据权限 effective_scope 单元测试（③）。

dept 无部门模型，退化为 self；is_super 或 data_scope==all 才放开跨用户可见。
"""
from __future__ import annotations

import pytest

from app.core.auth_deps import AuthUser, effective_scope


def _user(*, is_super: bool, data_scope: str) -> AuthUser:
    return AuthUser(
        id=1,
        username="u",
        display_name="U",
        is_super=is_super,
        data_scope=data_scope,
    )


@pytest.mark.parametrize(
    "is_super,data_scope,expected",
    [
        (True, "self", "all"),   # super 绕过一切
        (True, "all", "all"),
        (False, "all", "all"),   # 显式 all
        (False, "self", "self"),
        (False, "dept", "self"),  # dept 无部门模型 → 退化 self
    ],
)
def test_effective_scope(is_super, data_scope, expected):
    assert effective_scope(_user(is_super=is_super, data_scope=data_scope)) == expected


# ── API 层 scope 接线：ai-alerts 端点把 effective_scope 透传给 service ─────


@pytest.mark.parametrize(
    "is_super,data_scope,expected_scope",
    [
        (True, "self", "all"),
        (False, "self", "self"),
    ],
)
def test_ai_alerts_endpoint_passes_effective_scope(
    client, monkeypatch, is_super, data_scope, expected_scope
):
    from app.core.auth_deps import AuthUser, get_current_user
    from app.main import app
    from app.services import ai_alerts as alerts_svc_mod

    captured: dict = {}

    async def fake_list_alerts(db, user_id, **kw):
        captured.update(kw, user_id=user_id)
        return []

    monkeypatch.setattr(alerts_svc_mod, "list_alerts", fake_list_alerts)

    user = AuthUser(
        id=7,
        username="t",
        display_name="T",
        is_super=is_super,
        permission_codes=frozenset({"ai.watch"}),
        data_scope=data_scope,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = client.get("/api/ai-alerts")
        assert resp.status_code == 200
        assert captured["scope"] == expected_scope
        assert captured["user_id"] == 7
    finally:
        app.dependency_overrides.pop(get_current_user, None)
