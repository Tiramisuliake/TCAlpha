---
name: git-workflow
description: Git 工作流 / 提交规范 / 双远程（GitHub + Gitee）/ 分支策略 / 发布流程。触发词：Git、提交、commit、分支、merge、push、推送、远程
---

# Git 工作流

## 双远程约定

- `github` → https://github.com/Tiramisuliake/TCAlpha.git（主，公网展示）
- `gitee`  → https://gitee.com/tiramisulike/tcalpha.git（备，国内访问快）
- `origin` → 指向 github（默认 push 上行）

### 推送

```bash
git push github master       # 主推送
git push gitee master        # 同步备份
git push origin master       # 等价 github

# 或一次推所有
git push github master && git push gitee master
```

> ⚠️ 双远程不要用 `git remote set-url --add` 合并 push URL：万一其中一个挂会导致 fetch/pull 也异常。保持独立 remote。

## 分支策略（小团队简化版）

- `master`：主干，所有变更直接 push（个人版前期）
- 后期接入 PR 流程后：`feat/xxx` / `fix/xxx` / `chore/xxx` 短分支 → squash 合 master

## Commit 规范

格式：`<type>: <短描述>`

| type | 用途 |
|---|---|
| feat | 新功能 |
| fix | Bug 修复 |
| chore | 配置 / 工具 / 依赖更新 |
| refactor | 重构（不改外部行为） |
| docs | 文档 |
| test | 测试 |
| perf | 性能 |
| build | 构建（docker / CI） |
| release | 版本发布 |

### 好的 commit

```
feat: 接入 AKShare 日 K 下载（限流 2 req/s + Celery）

- 新增 services/data.py 的 fetch_daily_kline()
- tasks/data_tasks.py 加 download_one_symbol 任务
- ArcticDB bar_1d library 自动建库
- 测试覆盖：股票代码归一化 + 限流退避
```

### 坏的 commit

- `update` / `fix bug` / `wip`
- 一个提交改 30 个文件横跨多个模块

## 发布流程

1. 更新 `CHANGELOG.md`（顶部加新版本块）
2. 后端 `pyproject.toml` + 前端 `package.json` 版本号同步
3. `git commit -m "release: v0.x.y …"`
4. `git tag v0.x.y`
5. `git push github master --tags && git push gitee master --tags`
6. GitHub Release notes 复制 CHANGELOG 当版本块

## 禁止 / 警惕

- ❌ `git push --force master`（hook 会拦截）
- ❌ `git filter-branch` / `git filter-repo` 改历史
- ❌ `git commit --amend` 已 push 的提交
- ❌ `git reset --hard HEAD~N`（hook 会拦截）
- ⚠️ rebase 私有分支 OK，rebase 公共分支谨慎

## 紧急回滚

```bash
git revert <commit>             # 推荐：创建反向提交
git push github master && git push gitee master
```

不要 `reset --hard + force push`。
