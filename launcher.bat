@echo off
chcp 65001 >nul 2>&1
REM Dy-Sentry 启动器：启动服务并在 2 秒后打开预览页
start "" cmd /c "timeout /t 2 >nul & start "" http://localhost:12580/"
dy-sentry.exe
