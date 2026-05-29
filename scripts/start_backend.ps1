#requires -Version 5.1
# 启动 FastAPI 后端：清端口残留（含子进程树）+ 后台 health 探活 + 前台 uvicorn。
#
# 关键细节：
#   - UTF-8 with BOM + chcp 65001 → PS 5.1 中文不乱码
#   - **用 taskkill /F /T 替代 Stop-Process**，把 uvicorn --reload 的父子进程
#     整棵树砍光。Stop-Process 在 Windows 上对 --reload 子进程经常杀不动。
#   - 多轮验证：杀完后再 sleep + 重新扫，直到端口干净，避免"杀一批又重出现"
#   - 设 NO_PROXY 防 Clash 把 localhost 劫持
#   - 后台独立 PS 进程轮询 /health 显式禁代理，命中后打 ✅ banner

param(
    # 默认改 8001：8000 在某些 Windows 系统上有 TCP socket 泄漏，
    # 表现为 netstat 显示几个 LISTENING 但 taskkill 找不到进程，端口拿不回来。
    # 想坚持 8000 用 -Port 8000 覆盖。
    [int]$Port = 8001,
    [string]$BindHost = "127.0.0.1"
)

chcp 65001 > $null
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = "localhost,127.0.0.1,::1"

function Write-Banner($Text, $Color = "Cyan") {
    $line = ("─" * 56)
    Write-Host ""
    Write-Host $line -ForegroundColor $Color
    Write-Host $Text -ForegroundColor $Color
    Write-Host $line -ForegroundColor $Color
}

function Get-PortListeners($Port) {
    Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Where-Object { $_.State -eq 'Listen' } |
        Select-Object -ExpandProperty OwningProcess -Unique
}

function Clear-Port($Port, [int]$MaxRounds = 3) {
    for ($round = 1; $round -le $MaxRounds; $round++) {
        $pids = Get-PortListeners $Port
        if (-not $pids) {
            return $true
        }
        Write-Host ("      第 {0} 轮：发现 {1} 个监听进程" -f $round, @($pids).Count) -ForegroundColor Yellow
        foreach ($procId in $pids) {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            $name = if ($proc) { $proc.ProcessName } else { "<exited>" }
            Write-Host ("        ✗ taskkill /F /T PID={0} ({1})" -f $procId, $name) -ForegroundColor Yellow
            # /F 强杀 /T 杀整棵子进程树，对 uvicorn --reload 父子结构必备
            cmd /c "taskkill /F /T /PID $procId" 2>&1 | Out-Null
        }
        Start-Sleep -Milliseconds 1200
    }
    # 仍有残留就告警
    $remaining = Get-PortListeners $Port
    if ($remaining) {
        Write-Host ("      ⚠ 仍有 {0} 个监听进程未清除（PID: {1}）" -f @($remaining).Count, ($remaining -join ',')) -ForegroundColor Red
        Write-Host "      请用任务管理器手动结束这些 PID，或以管理员身份重跑本脚本。" -ForegroundColor Red
        return $false
    }
    return $true
}

Write-Banner "▶ TCAlpha 后端启动器  ${BindHost}:${Port}" "Cyan"

if ($env:http_proxy -or $env:https_proxy -or $env:HTTP_PROXY -or $env:HTTPS_PROXY) {
    $px = if ($env:http_proxy) { $env:http_proxy } else { $env:HTTP_PROXY }
    Write-Host "ℹ️  检测到系统代理 ($px)；脚本已设 NO_PROXY=localhost。" -ForegroundColor DarkYellow
}

# ── 1. 清端口残留（多轮 taskkill /F /T）────────────────────────
Write-Host "[1/3] 清理端口 $Port 残留进程..." -ForegroundColor White
$cleaned = Clear-Port $Port
if ($cleaned) {
    Write-Host "      ✓ 端口干净" -ForegroundColor Green
} else {
    Write-Host "      ✗ 清理未完全成功，仍尝试启动 uvicorn（可能仍会 bind 失败）" -ForegroundColor Red
}

# ── 2. 后台 health watcher（独立 PS 进程，显式禁代理）─────────
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
            Write-Host '  按 Ctrl+C 停止 uvicorn' -ForegroundColor Green
            Write-Host '════════════════════════════════════════════════════════' -ForegroundColor Green
            Write-Host ''
            return
        }
    } catch { }
    Start-Sleep -Milliseconds 500
}
Write-Host ''
Write-Host '⚠️  30s 内 /health 未返回 200。可能原因：' -ForegroundColor Yellow
Write-Host '    1) DB / Redis 未启动，lifespan 卡住（看本窗口 uvicorn log）' -ForegroundColor Yellow
Write-Host '    2) 端口还有僵尸进程派发请求，请：' -ForegroundColor Yellow
Write-Host '       netstat -ano | findstr ":${Port}\s.*LISTENING"' -ForegroundColor Yellow
Write-Host '       如多于 1 个 PID 说明清理失败，请手动 taskkill /F /T /PID <pid>' -ForegroundColor Yellow
Write-Host ''
"@

$watcher = Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $watcherScript) `
    -NoNewWindow -PassThru

# ── 3. 前台启动 uvicorn ─────────────────────────────────────────
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
