@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Stop All HMI Services (Windows)
REM Stops: Nginx (Frontend Proxy) + Flask Backend
REM ============================================================================

echo ============================================================================
echo Stopping All HMI Services
echo ============================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM ============================================================================
REM STEP 1: Stop Nginx
REM ============================================================================
echo [1/2] Stopping Nginx...

tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
if !errorlevel! equ 0 (
    REM Try graceful shutdown first using nginx -s quit
    if exist "nginx-1.28.0\nginx.exe" (
        echo Attempting graceful shutdown...
        cd nginx-1.28.0
        nginx.exe -s quit
        cd ..
        timeout /t 2 /nobreak >nul
    )
    
    REM Force kill if still running
    tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
    if !errorlevel! equ 0 (
        echo Force stopping nginx...
        taskkill /F /IM nginx.exe >nul 2>&1
        echo [SUCCESS] Nginx stopped
    ) else (
        echo [SUCCESS] Nginx stopped gracefully
    )
) else (
    echo [INFO] Nginx is not running
)

echo.

REM ============================================================================
REM STEP 2: Stop Flask Backend
REM ============================================================================
echo [2/2] Stopping Flask Backend...

REM Kill all Python processes (Flask backend)
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if !errorlevel! equ 0 (
    echo Stopping Python processes...
    taskkill /F /IM python.exe >nul 2>&1
    if !errorlevel! equ 0 (
        echo [SUCCESS] Flask backend stopped
    ) else (
        echo [WARNING] Could not stop Python processes
    )
) else (
    echo [INFO] Flask backend is not running
)

echo.

REM Wait for ports to be released
timeout /t 2 /nobreak >nul

REM ============================================================================
REM VERIFY SHUTDOWN
REM ============================================================================
echo ============================================================================
echo Verifying All Services Stopped
echo ============================================================================
echo.

set ALL_STOPPED=1

REM Check Nginx
tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
if !errorlevel! equ 0 (
    echo [WARNING] Nginx is still running!
    set ALL_STOPPED=0
) else (
    echo [OK] Nginx stopped
)

REM Check Flask Backend
netstat -ano | findstr ":6001" >nul 2>&1
if !errorlevel! equ 0 (
    echo [WARNING] Port 6001 is still in use!
    set ALL_STOPPED=0
) else (
    echo [OK] Flask backend stopped
)

echo.

if !ALL_STOPPED!==1 (
    echo ============================================================================
    echo All Services Stopped Successfully
    echo ============================================================================
    echo.
    echo To start services: start_all_services.bat
    echo.
) else (
    echo ============================================================================
    echo WARNING: Some Services May Still Be Running
    echo ============================================================================
    echo.
    echo Please check manually:
    echo   tasklist ^| findstr "nginx.exe"
    echo   netstat -ano ^| findstr ":6001"
    echo.
    echo You may need to restart your computer if services won't stop.
    echo.
)
