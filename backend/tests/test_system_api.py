"""系统管理路由测试（Phase 7 v0.7.2）。

只覆盖权限闸门 + DTO 流；CRUD 的业务行为留给后续 service 单测，
这里聚焦"前端调到对路径 + 权限对了不对"。
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.auth_deps import AuthUser, get_current_user
from app.main import app

ADMIN = AuthUser(
    id=1,
    username="admin",
    display_name="Admin",
    is_super=True,
    role_codes=frozenset({"admin"}),
    permission_codes=frozenset(),
    data_scope="all",
)

VIEWER = AuthUser(
    id=3,
    username="viewer",
    display_name="Viewer",
    is_super=False,
    role_codes=frozenset({"viewer"}),
    permission_codes=frozenset({"strategy.read"}),  # 没 system.* 权限
    data_scope="self",
)


@pytest.fixture(autouse=True)
def _ensure_engine():
    import app.db.postgres as pg
    if pg.async_session_factory is None:
        pg.init_engine()
    yield


@pytest.fixture
def as_user():
    def _setter(user: AuthUser | None) -> None:
        if user is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = lambda: user

    yield _setter
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ── 401 ────────────────────────────────────────────────────────────


def test_no_token_blocks_system_users(client):
    r = client.get("/api/system/users")
    assert r.status_code == 401


def test_no_token_blocks_system_roles(client):
    r = client.get("/api/system/roles")
    assert r.status_code == 401


# ── viewer：无 system.* 权限，全部 403 ────────────────────────────


def test_viewer_cannot_list_users(client, as_user):
    as_user(VIEWER)
    r = client.get("/api/system/users")
    assert r.status_code == 403
    assert "system.user.read" in r.json()["detail"]


def test_viewer_cannot_list_roles(client, as_user):
    as_user(VIEWER)
    r = client.get("/api/system/roles")
    assert r.status_code == 403
    assert "system.role.read" in r.json()["detail"]


def test_viewer_cannot_create_user(client, as_user):
    as_user(VIEWER)
    r = client.post(
        "/api/system/users",
        json={"username": "x", "password": "12345678", "role_codes": []},
    )
    assert r.status_code == 403
    assert "system.user.write" in r.json()["detail"]


def test_viewer_cannot_create_role(client, as_user):
    as_user(VIEWER)
    r = client.post(
        "/api/system/roles",
        json={"code": "x", "name": "X"},
    )
    assert r.status_code == 403
    assert "system.role.write" in r.json()["detail"]


# ── admin (super)：闸门全过 ───────────────────────────────────────


def test_admin_lists_roles(client, as_user):
    as_user(ADMIN)
    r = client.get("/api/system/roles")
    assert r.status_code == 200
    codes = [r["code"] for r in r.json()]
    # 种子里至少有 admin / trader / viewer
    assert "admin" in codes
    assert "trader" in codes
    assert "viewer" in codes


def test_admin_lists_permissions(client, as_user):
    as_user(ADMIN)
    r = client.get("/api/system/permissions")
    assert r.status_code == 200
    items = r.json()
    # 种子里至少 18 个
    assert len(items) >= 18
    cats = {p["category"] for p in items}
    assert {"system", "strategy", "sim", "backtest", "data", "ai", "notify"} <= cats


def test_admin_lists_users(client, as_user):
    as_user(ADMIN)
    r = client.get("/api/system/users")
    assert r.status_code == 200
    items = r.json()
    # 至少有 id=1 的 admin
    admin = next((u for u in items if u["id"] == 1), None)
    assert admin is not None
    assert "admin" in admin["role_codes"]
    assert admin["is_super"] is True


def test_admin_get_role_detail(client, as_user):
    as_user(ADMIN)
    # 先列表拿到 admin role id
    list_r = client.get("/api/system/roles")
    admin_role = next(r for r in list_r.json() if r["code"] == "admin")
    role_id = admin_role["id"]

    r = client.get(f"/api/system/roles/{role_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == "admin"
    # admin 角色绑了所有权限
    assert len(body["permission_codes"]) >= 18


# ── 防自残：admin 不能删自己 ─────────────────────────────────────


def test_admin_cannot_delete_self(client, as_user):
    as_user(ADMIN)
    r = client.delete(f"/api/system/users/{ADMIN.id}")
    assert r.status_code == 400
    assert "yourself" in r.json()["detail"]


def test_admin_cannot_deactivate_self(client, as_user):
    as_user(ADMIN)
    r = client.put(
        f"/api/system/users/{ADMIN.id}",
        json={"is_active": False},
    )
    assert r.status_code == 400
    assert "yourself" in r.json()["detail"]


def test_admin_cannot_delete_admin_role(client, as_user):
    as_user(ADMIN)
    list_r = client.get("/api/system/roles")
    admin_role = next(r for r in list_r.json() if r["code"] == "admin")
    r = client.delete(f"/api/system/roles/{admin_role['id']}")
    assert r.status_code == 400
    assert "admin" in r.json()["detail"]
