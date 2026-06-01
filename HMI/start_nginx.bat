@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Start Nginx Frontend Proxy
REM HTTP: 8080  |  HTTPS: 8443
REM ============================================================================

cd /d "%~dp0"
if not exist "logs\" mkdir logs

echo ============================================================
echo   Starting Nginx Proxy  ^|  HTTP: 8080  ^|  HTTPS: 8443
echo ============================================================
echo.

REM Check if nginx binary exists
if not exist "nginx-1.28.0\nginx.exe" (
    echo [ERROR] Nginx not found at nginx-1.28.0\nginx.exe
    echo Please ensure Nginx is placed in the HMI\nginx-1.28.0\ folder.
    pause
    exit /b 1
)

REM Check if already running
tasklist /FI "IMAGENAME eq nginx.exe" 2>nul | find /I "nginx.exe" >nul
if %errorlevel% equ 0 (
    echo [WARNING] Nginx is already running.
    pause
    exit /b 0
)

echo Starting Nginx...
cd nginx-1.28.0
start "Nginx Proxy" /B nginx.exe
cd ..

timeout /t 2 /nobreak >nul

REM Verify
tasklist /FI "IMAGENAME eq nginx.exe" 2>nul | find /I "nginx.exe" >nul
if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Nginx is running:
    echo   HTTP  ^> http://localhost:8080
    echo   HTTPS ^> https://localhost:8443
) else (
    echo [ERROR] Nginx failed to start.
    echo Check nginx-1.28.0\logs\error.log for details.
)

echo.
pause
