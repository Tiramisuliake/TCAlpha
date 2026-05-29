@echo off
REM TCAlpha backend launcher (double-click to run).
REM
REM Behavior:
REM   1. Calls scripts/start_backend.ps1
REM   2. The PS script clears stale uvicorn on port 8001
REM   3. Starts uvicorn --reload on http://127.0.0.1:8001
REM
REM Press Ctrl+C in the window to stop the backend.
REM
REM Note: keep this .bat as pure ASCII; CMD decodes the file as GBK
REM and any non-ASCII chars become mojibake and get parsed as commands.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_backend.ps1"

echo.
echo [start-backend] uvicorn exited, press any key to close window...
pause >nul
