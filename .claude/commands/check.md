# /check — 全栈代码规范检查

跑后端 + 前端的 lint + typecheck + 测试，输出整改建议。

## 步骤

```bash
# 后端
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy app
uv run pytest

# 前端
cd ../frontend
pnpm typecheck
pnpm lint   # 若有 eslint 配置
pnpm build  # 验证可构建
```

## 把发现的问题分级

| 等级 | 处理 |
|---|---|
| 错误（type 错 / lint 错 / 测试失败） | 立即修复 |
| 警告（unused / 命名不规范） | 列出但用户决定 |
| 建议（重构 / 性能 / 可读性） | 列出供参考 |

## 输出格式

```markdown
## 检查报告

### 错误 (必须修)
- backend/app/services/x.py:45 — mypy 类型不匹配
- frontend/src/pages/Y/index.tsx:120 — 缺少 onClick 类型

### 警告
- ... 

### 建议
- ...

### 自动修复建议
跑这些命令可自动修一部分：
```bash
cd backend && uv run ruff check . --fix && uv run ruff format .
```
```

## 不做

- 不直接 commit 修改（让用户决定）
- 不擅自删 unused（可能是预留接口）
