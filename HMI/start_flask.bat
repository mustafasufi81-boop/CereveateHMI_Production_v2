@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Start Flask HMI Backend (app.py) on port 6001
REM ============================================================================

cd /d "%~dp0"
if not exist "logs\" mkdir logs

echo ============================================================
echo   Starting Flask HMI Backend  ^|  Port: 6001
echo ============================================================
echo.

REM Check if already running
netstat -ano | findstr ":6001" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARNING] Port 6001 is already in use - Flask may already be running.
    pause
    exit /b 0
)

REM Check virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\
    echo Please run: python -m venv .venv
    echo Then run:   .venv\Scripts\pip install -r requirements-production.txt
    pause
    exit /b 1
)

echo Starting Flask HMI Backend...
start "Flask HMI Backend" cmd /k ".venv\Scripts\python.exe app.py"

REM Wait and verify
echo Waiting for Flask to start...
set /a RETRY=0
:wait_flask
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":6001" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] Flask HMI Backend is running at http://localhost:6001
    echo.
    goto :end
)
set /a RETRY+=1
if !RETRY! lss 15 (
    echo   Waiting... !RETRY!/15
    goto :wait_flask
)

echo [ERROR] Flask HMI Backend did not start within 15 seconds.
echo Check the console window for errors.

:end
pause
