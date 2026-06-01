@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Start MQTT Real-Time Publisher (mqtt_publisher_realtime_from_db.py)
REM Reads tag values from historian_timeseries and publishes to MQTT broker
REM Broker: 127.0.0.1:1883  |  Publish interval: 2 seconds
REM ============================================================================

cd /d "%~dp0"
if not exist "logs\" mkdir logs

echo ============================================================
echo   Starting MQTT Real-Time Publisher
echo   Broker: 127.0.0.1:1883  ^|  Interval: 2s
echo ============================================================
echo.

REM Check virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found at .venv\
    echo Please run: python -m venv .venv
    echo Then run:   .venv\Scripts\pip install -r requirements-production.txt
    pause
    exit /b 1
)

REM Check MQTT broker reachability (optional warning)
netstat -ano | findstr ":1883" | findstr "LISTENING" >nul 2>&1
if not %errorlevel% equ 0 (
    echo [WARNING] MQTT broker does not appear to be running on port 1883.
    echo           The publisher will keep retrying - continue anyway.
    echo.
)

echo Starting MQTT Real-Time Publisher...
echo Log: logs\mqtt_publisher.log
echo.
start "MQTT Publisher" cmd /k ".venv\Scripts\python.exe mqtt_publisher_realtime_from_db.py"

echo [INFO] MQTT Publisher window opened.
echo.
pause
