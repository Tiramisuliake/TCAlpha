#!/usr/bin/env node
/**
 * PreToolUse Hook — TCAlpha (Python + FastAPI + React + Celery)
 * 1. 阻止真正危险的命令
 * 2. 对敏感操作给提醒
 * 3. 检测 Windows nul 重定向陷阱
 */

const fs = require('fs');

let inputData = '';
try { inputData = fs.readFileSync(0, 'utf8'); } catch { process.exit(0); }

let input;
try { input = JSON.parse(inputData); } catch { process.exit(0); }

const toolName = input.tool_name;
const toolInput = input.tool_input || {};

function output(obj) { console.log(JSON.stringify(obj)); process.exit(0); }

// ─────────────────────────────────────────────────────────────
// Bash
// ─────────────────────────────────────────────────────────────
if (toolName === 'Bash') {
  const command = toolInput.command || '';

  // Windows nul 重定向陷阱（会创建名为 nul 的文件）
  if (/[12]?\s*>\s*nul\b/i.test(command)) {
    output({
      decision: 'block',
      reason: '❌ `> nul` 在 Windows 会创建一个名为 nul 的文件。请用 `> /dev/null 2>&1`（git bash）或移除输出重定向。\n命令: `' + command + '`',
    });
  }

  // 真正危险 — 直接阻止
  const dangerous = [
    { p: /rm\s+-rf\s+\/(?!\w)/, why: '删除根目录' },
    { p: /rm\s+-rf\s+\*/, why: '删除所有文件' },
    { p: /\bdrop\s+(database|table)\b/i, why: '删除数据库/表（SQL）' },
    { p: /\btruncate\s+table\b/i, why: '清空表' },
    { p: /\bdrop\s+schema\b/i, why: '删除 schema' },
    { p: /git\s+push\s+(-f|--force)\s+(origin|github|gitee)?\s*(master|main)\b/i, why: '强制推送主分支' },
    { p: /git\s+reset\s+--hard\s+HEAD~\d+/, why: '硬重置多个提交（不可恢复）' },
    { p: /git\s+filter-(branch|repo)/, why: '改写历史会破坏其他人 clone' },
    { p: />\s*\/dev\/sd[a-z]/, why: '直接写入磁盘设备' },
    { p: /mkfs\./, why: '格式化文件系统' },
    { p: /:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;/, why: 'fork 炸弹' },
    // 数据库 / 容器破坏
    { p: /docker\s+(compose\s+)?down\s+(-v|--volumes)\b/, why: '会删除数据库 volume（PG/Redis 数据丢失）' },
    { p: /docker\s+volume\s+(prune|rm)\b.*pgdata/, why: '删除 PG volume' },
    // 包发布（不可撤回）
    { p: /\bpypi-publish\b|\btwine\s+upload\b/, why: '发布到 PyPI 不可撤回' },
    { p: /\bnpm\s+publish\b(?!\s+--dry-run)/, why: '发布到 npm 不可撤回' },
    // 迁移降级到根（破坏数据）
    { p: /alembic\s+downgrade\s+base\b/, why: 'Alembic 降级到 base 会清空所有表' },
  ];
  for (const { p, why } of dangerous) {
    if (p.test(command)) {
      output({
        decision: 'block',
        reason: '⚠️ 危险操作已阻止\n命令: `' + command + '`\n原因: ' + why + '\n\n如确需执行，请手动在终端运行。',
      });
    }
  }

  // 警告但放行
  const warn = [
    { p: /git\s+push\s+(-f|--force)\b/, m: 'force push 可能覆盖他人提交' },
    { p: /git\s+rebase\b/, m: 'rebase 会改写提交历史，确保是私有分支' },
    { p: /docker\s+compose\s+down\b/, m: '会停止 PG/Redis（不会删 volume，数据保留）' },
    { p: /alembic\s+downgrade\b/, m: 'Alembic 降级会丢失对应版本之后的数据' },
    { p: /pnpm\s+(install|add)\s+--force/, m: '强制装依赖可能引入版本冲突' },
    { p: /uv\s+sync\s+--reinstall\b/, m: '重装所有依赖会比较慢' },
    { p: /pytest\s+.*--no-cov\b/, m: '关闭覆盖率统计（仅调试时建议）' },
    { p: /celery\s+.*--purge\b/, m: '会清空 Redis broker 中所有任务' },
  ];
  for (const { p, m } of warn) {
    if (p.test(command)) {
      output({ continue: true, systemMessage: '⚠️ ' + m });
    }
  }
}

// ─────────────────────────────────────────────────────────────
// Write — 敏感文件提醒
// ─────────────────────────────────────────────────────────────
if (toolName === 'Write') {
  const filePath = (toolInput.file_path || '').replace(/\\/g, '/');

  const sensitive = [
    { suffix: '.env', m: '不要提交真实密钥（应只改 .env.example）' },
    { suffix: '.env.production', m: '生产环境密钥，禁止提交到 git' },
    { suffix: '.env.local', m: '本地环境变量，禁止提交' },
    { suffix: 'docker-compose.prod.yml', m: '生产 compose 配置，注意是否含明文密码' },
    { suffix: 'alembic.ini', m: '注意 sqlalchemy.url 是否硬编码生产密码' },
  ];
  for (const { suffix, m } of sensitive) {
    if (filePath.endsWith(suffix)) {
      output({ continue: true, systemMessage: '🔒 敏感文件 `' + suffix + '`：' + m });
    }
  }

  // 提醒 alembic 自动迁移文件
  if (/alembic\/versions\/.*\.py$/.test(filePath)) {
    output({ continue: true, systemMessage: '📜 写入 alembic 迁移：人工 review upgrade/downgrade 是否对称、是否有破坏性变更' });
  }
}

output({ continue: true });
