---
name: alembic-migration
description: Alembic 迁移 / autogenerate / upgrade / downgrade / 数据迁移。触发词：Alembic、迁移、migrate、upgrade、downgrade、autogenerate、schema 变更
---

# Alembic 迁移

## 基本命令

```bash
# 在 backend/ 下
uv run alembic revision --autogenerate -m "add x_field"   # 生成迁移
uv run alembic upgrade head                                # 应用到最新
uv run alembic downgrade -1                                # 回退一步
uv run alembic current                                     # 当前版本
uv run alembic history                                     # 历史
```

`make` 快捷：

```bash
make migrate                            # upgrade head
make revision m="add x_field"           # 等价 revision --autogenerate
```

## 配置

- `alembic.ini` 用同步 URL（psycopg2）
- `alembic/env.py` 从 `app.config.settings.database_url_sync` 读
- `alembic/env.py` import `app.db.models` 让 autogenerate 看到所有模型

## 工作流

1. 改 `app/db/models/<x>.py`（或加新模型）
2. 在 `app/db/models/__init__.py` re-export 新模型
3. `make revision m="describe what changed"`
4. **打开生成的迁移文件 review**：
   - 字段名 / 类型对不对？
   - 索引建对了？
   - `downgrade()` 是否对称？
5. `make migrate`

## 一次只做一件事

每个迁移文件只做一类变更。复杂变更拆多个迁移：

```
0001 add_users
0002 add_strategy_configs
0003 add_status_index_on_strategy
```

不要"批量大杂烩"迁移，回滚时会撕裂。

## 手写迁移（autogenerate 漏的）

某些情况 autogenerate 不识别：
- 字段重命名（会看成 drop + add）
- check 约束变更
- 数据迁移

需要手写：

```python
def upgrade() -> None:
    # schema 变更
    op.alter_column("users", "username", new_column_name="login")
    # 数据迁移
    op.execute("UPDATE users SET role='admin' WHERE id=1")

def downgrade() -> None:
    op.execute("UPDATE users SET role=NULL WHERE id=1")
    op.alter_column("users", "login", new_column_name="username")
```

## 危险动作（生产慎用）

| 操作 | 风险 | 替代 |
|---|---|---|
| `drop_column` | 数据永久丢失 | 先发版只停用、隔一版才 drop |
| `alter_column` 改类型 | 大表锁表 | 先加新字段 + 双写 + 切读 + 删旧字段 |
| `drop_table` | 数据全没 | 先 rename + 一段时间后再 drop |
| `downgrade base` | 清空所有表 | hook 已拦截 |

## 多 head 解决

```bash
alembic heads                              # 看是否多 head
alembic merge -m "merge x and y" head1 head2
alembic upgrade head
```

## 数据填充

业务种子数据不要放迁移文件（变更频繁）。
迁移只做 schema；初始数据写独立脚本 `scripts/seed.py` 或在 lifespan / 命令行任务里跑。

## 测试中

测试用独立 DB，conftest 启动时 `alembic upgrade head`，结束时 `downgrade base`。
