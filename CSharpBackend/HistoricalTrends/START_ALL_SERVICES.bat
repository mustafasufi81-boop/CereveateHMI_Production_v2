@echo off
REM ================================================================
REM BACKGROUND SERVICES STARTUP SCRIPT
REM Starts all background services for the SCADA system
REM ================================================================

echo.
echo ================================================================
echo CEREVEATE OPC SCADA - BACKGROUND SERVICES STARTUP
echo ================================================================
echo.

cd /d "%~dp0"

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script requires administrator privileges!
    echo Please right-click and select "Run as Administrator"
    pause
    exit /b 1
)

echo [1/3] Checking Python environment...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Python not found! Please install Python first.
    pause
    exit /b 1
)
echo   ✓ Python found

echo.
echo [2/3] Starting ML Background Learning Service...
cd ML_System

REM Check if service is already installed
sc query MLBackgroundLearningSystem >nul 2>&1
if %errorLevel% equ 0 (
    echo   Service already installed. Starting...
    sc start MLBackgroundLearningSystem
    if %errorLevel% equ 0 (
        echo   ✓ ML Background Service started
    ) else (
        echo   ⚠ Service start failed (may already be running)
    )
) else (
    echo   Installing service...
    python ml_background_service.py install
    if %errorLevel% equ 0 (
        echo   ✓ Service installed
        echo   Starting service...
        sc start MLBackgroundLearningSystem
        if %errorLevel% equ 0 (
            echo   ✓ ML Background Service started
        ) else (
            echo   ✗ Service start failed
        )
    ) else (
        echo   ✗ Service installation failed
    )
)

cd ..

echo.
echo [3/3] Starting Flask Web Server with Downtime Monitoring...
echo   This will run Flask with integrated downtime tracking
echo   Press Ctrl+C to stop
echo.

REM Kill any existing Python Flask processes
taskkill /F /IM python.exe /FI "WINDOWTITLE eq app.py*" >nul 2>&1

REM Start Flask with downtime monitoring
start /B "" python.exe app.py

echo.
echo ================================================================
echo STARTUP COMPLETE
echo ================================================================
echo.
echo Services Running:
echo   1. ML Background Learning Service (Windows Service)
echo   2. Flask Web Server (port 5002)
echo   3. Downtime Monitoring (integrated with Flask)
echo.
echo Web Interface: http://127.0.0.1:5002
echo.
echo To stop services:
echo   - Press Ctrl+C to stop Flask
echo   - Run: sc stop MLBackgroundLearningSystem
echo.
pause
