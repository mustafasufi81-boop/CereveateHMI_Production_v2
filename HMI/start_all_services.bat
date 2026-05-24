@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Start All HMI Services (Windows)
REM Starts: Nginx (Frontend Proxy) + Flask Backend (Eventlet)
REM ============================================================================

echo ============================================================================
echo Starting All HMI Services
echo ============================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Create logs directory if it doesn't exist
if not exist "logs\" mkdir logs

REM ============================================================================
REM STEP 1: Start Flask Backend (Eventlet)
REM ============================================================================
echo [1/2] Starting Flask Backend (Eventlet on port 6001)...
echo.

REM Check if backend is already running
netstat -ano | findstr ":6001" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARNING] Port 6001 is already in use!
    echo Flask backend may already be running.
    echo.
    goto :start_nginx
)

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then run: venv\Scripts\pip install -r requirements-production.txt
    goto :error
)

REM Start Flask backend using start /B (background)
start /B cmd /c "venv\Scripts\activate.bat && python app.py > logs\hmi_startup.log 2>&1"

REM Wait for backend to start (retry up to 15 seconds)
echo Waiting for Flask backend to start...
set /a RETRY_COUNT=0
set /a MAX_RETRIES=15

:check_flask_port
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":6001" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [SUCCESS] Flask backend started on http://localhost:6001
    goto :flask_started
)

set /a RETRY_COUNT+=1
if !RETRY_COUNT! lss !MAX_RETRIES! (
    echo   Attempt !RETRY_COUNT!/!MAX_RETRIES! - waiting...
    goto :check_flask_port
)

echo [ERROR] Flask backend failed to start after !MAX_RETRIES! seconds!
echo Check logs\hmi_app.log for details
goto :error

:flask_started

echo.

REM ============================================================================
REM STEP 2: Start Nginx (Frontend Proxy)
REM ============================================================================
:start_nginx
echo [2/2] Starting Nginx (Port 8080 HTTP, 8443 HTTPS)...
echo.

REM Check if local nginx exists
if not exist "nginx-1.28.0\nginx.exe" (
    echo [ERROR] Nginx not found at nginx-1.28.0\nginx.exe
    echo Please ensure nginx is installed in the HMI\nginx-1.28.0\ folder
    goto :error
)

REM Check if nginx is already running
tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
if %errorlevel% equ 0 (
    echo [WARNING] Nginx is already running!
    echo.
    goto :success
)

REM Start nginx from local folder
cd nginx-1.28.0
start /B nginx.exe
cd ..

REM Wait for nginx to start
timeout /t 2 /nobreak >nul

REM Verify nginx started
tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
if %errorlevel% equ 0 (
    echo [SUCCESS] Nginx started successfully
    echo.
    echo Nginx is serving:
    echo   HTTP:  http://localhost:8080
    echo   HTTPS: https://localhost:8443
) else (
    echo [ERROR] Nginx failed to start!
    echo Check nginx-1.28.0\logs\error.log for details
    goto :error
)

echo.

REM ============================================================================
REM SUCCESS
REM ============================================================================
:success
echo ============================================================================
echo All Services Started Successfully
echo ============================================================================
echo.
echo Services running:
echo   [1] Flask Backend:  http://localhost:6001
echo   [2] Nginx Proxy:    http://localhost:8080 (HTTP)
echo   [3] Nginx Proxy:    https://localhost:8443 (HTTPS)
echo.
echo Access your HMI at:
echo   HTTP:  http://localhost:8080
echo   HTTPS: https://localhost:8443
echo.
echo To stop services:   stop_all_services.bat
echo To restart:         restart_all_services.bat
echo To check status:    status_all_services.bat
echo.
goto :end

REM ============================================================================
REM ERROR HANDLING
REM ============================================================================
:error
echo.
echo ============================================================================
echo ERROR: Failed to start all services
echo ============================================================================
echo.
echo Check the following:
echo   1. Virtual environment is set up: venv\Scripts\activate.bat
echo   2. Dependencies installed: pip install flask flask-socketio eventlet
echo   3. Nginx is present: nginx-1.28.0\nginx.exe
echo   4. Ports 6001, 8080, 8443 are not in use
echo   5. Check logs: logs\hmi_app.log and nginx-1.28.0\logs\error.log
echo.
exit /b 1

:end
