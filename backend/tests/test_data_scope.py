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
