#requires -Version 5.1
# 启动 FastAPI 后端：自动选干净端口（绕开 Windows tcpip.sys 幽灵 socket 泄漏）。
#
# 关键细节：
#   - UTF-8 with BOM + chcp 65001 → PS 5.1 中文不乱码
#   - 端口选择：从 -PortStart 开始尝试 -PortRange 个端口，跳过任何含 LISTENING 的
#   - 写入 `frontend/.dev-port` 让 vite.config.ts 动态读取代理目标
#   - 后台独立 PS 进程显式禁代理后轮询 /health，命中后打 ✅ banner
#   - 主进程前台跑 uvicorn，Ctrl+C 时 finally 杀 watcher
#
# Windows tcpip.sys 幽灵 socket 说明：
#   uvicorn --reload 子进程异常退出时，内核可能不释放 socket 句柄，
#   表现为 Get-NetTCPConnection 看得到 PID 但 Get-Process 找不到（taskkill 杀不动）。
#   这类幽灵需要重启电脑或 `netsh int ip reset` 才能清。本脚本绕开这种端口。

param(
    [int]$PortStart = 8001,
    [int]$PortRange = 50,
    [string]$BindHost = "127.0.0.1",
    [string]$PortFile = ""   # 默认写到 frontend/.dev-port
)

chcp 65001 > $null
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = "localhost,127.0.0.1,::1"

# 计算 PortFile 默认路径（脚本所在 → 仓库根 → frontend/.dev-port）
if ([string]::IsNullOrEmpty($PortFile)) {
    $repoRoot = Split-Path -Parent $PSScriptRoot
    $PortFile = Join-Path $repoRoot "frontend\.dev-port"
}

function Write-Banner($Text, $Color = "Cyan") {
    $line = ("─" * 56)
    Write-Host ""
    Write-Host $line -ForegroundColor $Color
    Write-Host $Text -ForegroundColor $Color
    Write-Host $line -ForegroundColor $Color
}

function Test-PortFree($Port) {
    # 任何状态的 TCP 条目（Listen / SynReceived / 幽灵）都算占用
    $conns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return -not $conns
}

function Find-FreePort($Start, $Range) {
    for ($p = $Start; $p -lt ($Start + $Range); $p++) {
        if (Test-PortFree $p) {
            return $p
        }
    }
    return 0
}

Write-Banner "▶ TCAlpha 后端启动器" "Cyan"

# ── 1. 选端口 ──────────────────────────────────────────────────
Write-Host "[1/3] 在 $PortStart .. $($PortStart + $PortRange - 1) 范围内找干净端口..." -ForegroundColor White
$Port = Find-FreePort $PortStart $PortRange
if ($Port -eq 0) {
    Write-Host "      ✗ 范围内无可用端口；请重启电脑清理 tcpip.sys 幽灵 socket。" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}
Write-Host "      ✓ 选定端口 $Port" -ForegroundColor Green

# 写入端口文件供前端读取
try {
    $portDir = Split-Path -Parent $PortFile
    if (-not (Test-Path $portDir)) {
        New-Item -ItemType Directory -Force -Path $portDir | Out-Null
    }
    [System.IO.File]::WriteAllText($PortFile, "$Port", [System.Text.UTF8Encoding]::new($false))
    Write-Host "      ✓ 端口写入 $PortFile（vite 自动读取）" -ForegroundColor Green
} catch {
    Write-Host "      ⚠ 端口文件写入失败：$_" -ForegroundColor Yellow
}

# ── 2. 后台 health watcher ────────────────────────────────────
Write-Host "[2/3] 启动后台 health 探活（30s 超时）..." -ForegroundColor White

$watcherScript = @"
chcp 65001 > `$null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(`$false)

`$env:NO_PROXY = 'localhost,127.0.0.1,::1'
`$env:http_proxy = ''
`$env:https_proxy = ''
`$env:HTTP_PROXY = ''
`$env:HTTPS_PROXY = ''
[System.Net.WebRequest]::DefaultWebProxy = `$null

`$url = 'http://${BindHost}:${Port}/health'
`$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt `$deadline) {
    try {
        `$r = Invoke-WebRequest -Uri `$url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if (`$r.StatusCode -eq 200) {
            Write-Host ''
            Write-Host '════════════════════════════════════════════════════════' -ForegroundColor Green
            Write-Host '  ✅  TCAlpha 后端启动成功！' -ForegroundColor Green
            Write-Host '  📡  API     → http://${BindHost}:${Port}' -ForegroundColor Green
            Write-Host '  📘  Swagger → http://${BindHost}:${Port}/docs' -ForegroundColor Green
            Write-Host '  ❤️   Health  → 200 OK' -ForegroundColor Green
            Write-Host '  👤  Dev 账号 → admin / 123456 （上线前请改密码）' -ForegroundColor Green
            Write-Host '  ℹ️   Vite 前端会自动读 frontend/.dev-port 转发到此端口' -ForegroundColor Green
            Write-Host '  按 Ctrl+C 停止 uvicorn' -ForegroundColor Green
            Write-Host '════════════════════════════════════════════════════════' -ForegroundColor Green
            Write-Host ''
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
Write-Host ''
Write-Host '⚠️  30s 内 /health 未返回 200。看本窗口 uvicorn log 排查 DB / Redis / lifespan。' -ForegroundColor Yellow
Write-Host ''
"@

$watcher = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $watcherScript) `
    -NoNewWindow -PassThru

# ── 3. 前台启动 uvicorn ────────────────────────────────────────
Write-Host "[3/3] 启动 uvicorn → http://${BindHost}:${Port}" -ForegroundColor White
Write-Host ""

try {
    uv --directory backend run uvicorn app.main:app --reload --host $BindHost --port $Port
} finally {
    if ($watcher -and -not $watcher.HasExited) {
        Stop-Process -Id $watcher.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Host "[start_backend] uvicorn exited." -ForegroundColor Cyan
}
