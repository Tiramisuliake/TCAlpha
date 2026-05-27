"""add rbac roles permissions and user fields

Revision ID: 7aaf2f5c947e
Revises: 3b597a00cb62
Create Date: 2026-05-27 16:29:24.314928

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7aaf2f5c947e'
down_revision: Union[str, None] = '3b597a00cb62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. permissions ────────────────────────────────────────────────
    op.create_table('permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=128), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False, server_default=''),
    sa.Column('description', sa.String(length=256), nullable=False, server_default=''),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_permissions_category'), 'permissions', ['category'], unique=False)
    op.create_index(op.f('ix_permissions_code'), 'permissions', ['code'], unique=True)

    # ── 2. roles ──────────────────────────────────────────────────────
    op.create_table('roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('data_scope', sa.String(length=16), nullable=False, server_default='self'),
    sa.Column('description', sa.String(length=256), nullable=False, server_default=''),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_roles_code'), 'roles', ['code'], unique=True)

    # ── 3. role_permissions ───────────────────────────────────────────
    op.create_table('role_permissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('permission_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('role_id', 'permission_id', name='uq_role_permission')
    )
    op.create_index(op.f('ix_role_permissions_permission_id'), 'role_permissions', ['permission_id'], unique=False)
    op.create_index(op.f('ix_role_permissions_role_id'), 'role_permissions', ['role_id'], unique=False)

    # ── 4. user_roles ─────────────────────────────────────────────────
    op.create_table('user_roles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('role_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'role_id', name='uq_user_role')
    )
    op.create_index(op.f('ix_user_roles_role_id'), 'user_roles', ['role_id'], unique=False)
    op.create_index(op.f('ix_user_roles_user_id'), 'user_roles', ['user_id'], unique=False)

    # ── 5. users 新增列（server_default 兼容已有 admin 行） ────────────
    op.add_column('users', sa.Column('display_name', sa.String(length=128), nullable=False, server_default=''))
    op.add_column('users', sa.Column('is_super', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True))

    # ── 6. seed：3 个角色 + 基础权限 + 已有 admin 标记 super 并绑 admin 角色 ─
    bind = op.get_bind()

    # 角色
    bind.execute(sa.text("""
        INSERT INTO roles (code, name, data_scope, description) VALUES
            ('admin',  '管理员', 'all',  '所有权限 + 所有数据'),
            ('trader', '操盘手', 'self', '策略 / 模拟交易 / 通知，仅本人数据'),
            ('viewer', '观察者', 'self', '只读，仅本人数据')
    """))

    # 权限点（核心集）
    seed_perms = [
        # category, code, name
        ('system',        'system.user.read',       '查看用户列表'),
        ('system',        'system.user.write',      '管理用户（增删改）'),
        ('system',        'system.role.read',       '查看角色'),
        ('system',        'system.role.write',      '管理角色 / 分配权限'),
        ('strategy',      'strategy.read',          '查看策略'),
        ('strategy',      'strategy.write',         '创建 / 编辑策略'),
        ('strategy',      'strategy.delete',        '删除策略'),
        ('strategy',      'strategy.run',           '启动 / 停止策略'),
        ('sim',           'sim.order.read',         '查看模拟订单'),
        ('sim',           'sim.order.cancel',       '撤销模拟订单'),
        ('backtest',      'backtest.read',          '查看回测'),
        ('backtest',      'backtest.run',           '提交回测'),
        ('data',          'data.read',              '查看行情数据'),
        ('data',          'data.download',          '触发数据下载'),
        ('ai',            'ai.chat',                'AI 助手对话'),
        ('ai',            'ai.watch',               'AI 盯盘 + watchlist'),
        ('notify',        'notify.rule.read',       '查看通知规则'),
        ('notify',        'notify.rule.write',      '管理通知规则'),
    ]
    for cat, code, name in seed_perms:
        bind.execute(
            sa.text("INSERT INTO permissions (code, name, category) VALUES (:c, :n, :cat)"),
            {"c": code, "n": name, "cat": cat},
        )

    # admin 角色绑所有权限
    bind.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT (SELECT id FROM roles WHERE code='admin'), id FROM permissions
    """))

    # trader 角色绑 strategy / sim / backtest / ai / notify / data 读+常规操作
    trader_perms = [
        'strategy.read', 'strategy.write', 'strategy.delete', 'strategy.run',
        'sim.order.read', 'sim.order.cancel',
        'backtest.read', 'backtest.run',
        'data.read', 'data.download',
        'ai.chat', 'ai.watch',
        'notify.rule.read', 'notify.rule.write',
    ]
    for code in trader_perms:
        bind.execute(
            sa.text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT (SELECT id FROM roles WHERE code='trader'),
                       (SELECT id FROM permissions WHERE code=:c)
            """),
            {"c": code},
        )

    # viewer 角色只绑 read
    viewer_perms = [
        'strategy.read', 'sim.order.read', 'backtest.read', 'data.read',
        'ai.chat', 'notify.rule.read',
    ]
    for code in viewer_perms:
        bind.execute(
            sa.text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT (SELECT id FROM roles WHERE code='viewer'),
                       (SELECT id FROM permissions WHERE code=:c)
            """),
            {"c": code},
        )

    # 把现有 id=1 用户（admin）标记 super 并绑 admin 角色（如果存在）
    bind.execute(sa.text("UPDATE users SET is_super = true WHERE id = 1"))
    bind.execute(sa.text("""
        INSERT INTO user_roles (user_id, role_id)
        SELECT 1, id FROM roles WHERE code='admin'
        ON CONFLICT (user_id, role_id) DO NOTHING
    """))


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'last_login_at')
    op.drop_column('users', 'is_super')
    op.drop_column('users', 'display_name')
    op.drop_index(op.f('ix_user_roles_user_id'), table_name='user_roles')
    op.drop_index(op.f('ix_user_roles_role_id'), table_name='user_roles')
    op.drop_table('user_roles')
    op.drop_index(op.f('ix_role_permissions_role_id'), table_name='role_permissions')
    op.drop_index(op.f('ix_role_permissions_permission_id'), table_name='role_permissions')
    op.drop_table('role_permissions')
    op.drop_index(op.f('ix_roles_code'), table_name='roles')
    op.drop_table('roles')
    op.drop_index(op.f('ix_permissions_code'), table_name='permissions')
    op.drop_index(op.f('ix_permissions_category'), table_name='permissions')
    op.drop_table('permissions')
    # ### end Alembic commands ###
