@echo off
REM TCAlpha backend launcher (double-click to run).
REM
REM Behavior:
REM   - Runs backend/run.py with the venv Python
REM   - run.py scans 8001..8050 for a real bindable port (skips tcpip.sys
REM     ghost LISTENING) and writes it to frontend/.dev-port for Vite
REM   - Starts uvicorn with --reload
REM
REM Note: keep this .bat as pure ASCII; CMD decodes the file as GBK
REM and any non-ASCII chars become mojibake and get parsed as commands.

set NO_PROXY=localhost,127.0.0.1,::1
set no_proxy=localhost,127.0.0.1,::1

"%~dp0backend\.venv\Scripts\python.exe" "%~dp0backend\run.py"

echo.
echo [start-backend] uvicorn exited, press any key to close window...
pause >nul
