@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Start MQTT HMI Dashboard (mqtt_app.py)
REM Displays real-time MQTT data from PostgreSQL (source='MQT')
REM ============================================================================

cd /d "%~dp0"
if not exist "logs\" mkdir logs

echo ============================================================
echo   Starting MQTT HMI Dashboard  ^|  mqtt_app.py
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

echo Starting MQTT HMI Dashboard...
echo Log: logs\mqtt_app.log
echo.
start "MQTT HMI Dashboard" cmd /k ".venv\Scripts\python.exe mqtt_app.py"

echo [INFO] MQTT HMI Dashboard window opened.
echo.
pause
