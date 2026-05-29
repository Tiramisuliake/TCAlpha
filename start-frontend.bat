@echo off
REM TCAlpha frontend launcher (double-click to run).
REM
REM Sets NO_PROXY so Vite's Node HTTP proxy does not route /api through
REM Clash/V2Ray when forwarding to the backend on 127.0.0.1.
REM
REM Note: keep this .bat as pure ASCII; CMD decodes the file as GBK
REM and any non-ASCII chars become mojibake and get parsed as commands.

cd /d "%~dp0"

set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1
set http_proxy=
set https_proxy=
set HTTP_PROXY=
set HTTPS_PROXY=

pnpm --dir frontend dev

echo.
echo [start-frontend] vite exited, press any key to close window...
pause >nul
