@echo off
REM ============================================================================
REM Stop Nginx Proxy
REM ============================================================================

echo Stopping Nginx...

cd /d "%~dp0"

if exist "nginx-1.28.0\nginx.exe" (
    cd nginx-1.28.0
    nginx.exe -s stop >nul 2>&1
    cd ..
)

timeout /t 2 /nobreak >nul
taskkill /IM nginx.exe /F >nul 2>&1

tasklist /FI "IMAGENAME eq nginx.exe" 2>nul | find /I "nginx.exe" >nul
if %errorlevel% equ 0 (
    echo [ERROR] Could not fully stop Nginx.
) else (
    echo [SUCCESS] Nginx stopped.
)
pause
