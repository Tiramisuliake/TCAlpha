"""add sim.order.place permission for manual trading

Revision ID: b1c2d3e4f5a6
Revises: 7aaf2f5c947e
Create Date: 2026-05-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '7aaf2f5c947e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 新增权限 sim.order.place
    bind.execute(sa.text("""
        INSERT INTO permissions (code, name, category, description)
        VALUES ('sim.order.place', '模拟下单', 'sim', '手工提交模拟交易订单')
        ON CONFLICT (code) DO NOTHING
    """))

    # 2. admin 角色：自动通过通配（admin 在原迁移中绑了所有权限）
    #    但 admin 是历史快照绑定，新权限需要手工补
    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT (SELECT id FROM roles WHERE code='admin'),
               (SELECT id FROM permissions WHERE code='sim.order.place')
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            JOIN roles r ON r.id = rp.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.code='admin' AND p.code='sim.order.place'
        )
    """))

    # 3. trader 角色：同样需要
    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT (SELECT id FROM roles WHERE code='trader'),
               (SELECT id FROM permissions WHERE code='sim.order.place')
        WHERE NOT EXISTS (
            SELECT 1 FROM role_permissions rp
            JOIN roles r ON r.id = rp.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.code='trader' AND p.code='sim.order.place'
        )
    """))


def downgrade() -> None:
    bind = op.get_bind()
    # 先删 role_permissions 引用，再删 permissions
    bind.execute(sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id = (SELECT id FROM permissions WHERE code='sim.order.place')
    """))
    bind.execute(sa.text("DELETE FROM permissions WHERE code='sim.order.place'"))
