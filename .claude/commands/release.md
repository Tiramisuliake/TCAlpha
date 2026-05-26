# /release — 发布新版本

按规范打 tag、推 GitHub + Gitee、生成 Release notes。

## 流程

### 1. 决定版本号

读 `backend/pyproject.toml` 当前版本 → 询问用户新版本号。
约定 SemVer：
- `major`：破坏性变更
- `minor`：新功能
- `patch`：bug 修复

### 2. 更新版本号（同步）

- `backend/pyproject.toml` `version = "x.y.z"`
- `frontend/package.json` `"version": "x.y.z"`

### 3. 更新 `CHANGELOG.md`

在顶部加新版本块：

```markdown
## v0.X.Y (YYYY-MM-DD)

### 新增
- ...

### 改进
- ...

### 修复
- ...

### 破坏性变更（如有）
- ...
```

### 4. 提交

```bash
git add backend/pyproject.toml frontend/package.json CHANGELOG.md
git commit -m "release: v0.X.Y — <一句话亮点>"
git tag v0.X.Y
```

### 5. 双推

```bash
git push github master --tags
git push gitee master --tags
```

### 6. GitHub Release（如有 gh CLI）

```bash
gh release create v0.X.Y --notes "$(awk '/^## v0.X.Y/,/^## v/' CHANGELOG.md | head -n -1)"
```

否则手动到 GitHub 创建 Release。

### 7. 输出报告

```markdown
## 已发布 v0.X.Y

- commit: <hash>
- tag: v0.X.Y
- github: https://github.com/Tiramisuliake/TCAlpha/releases/tag/v0.X.Y
- gitee:  https://gitee.com/tiramisulike/tcalpha/releases/tag/v0.X.Y
- changelog: 见 CHANGELOG.md
```

## 约束

- 禁止 force push tag
- 已发布的 tag 不能复用（删掉再 push 会破坏其他 clone）
- release commit 不要混业务变更
