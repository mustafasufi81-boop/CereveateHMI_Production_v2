@echo off
REM Manual Start Script for MQTT Services
REM Run ONE instance at a time

echo ============================================
echo Starting MQTT Services Manually
echo ============================================
echo.

REM Start Mosquitto
echo [1/2] Starting Mosquitto Broker...
start "Mosquitto Broker" "C:\Program Files\mosquitto\mosquitto.exe" -c "%~dp0mosquitto_test.conf" -v
timeout /t 3 /nobreak >nul
echo       [OK] Mosquitto started

REM Start MQTT Subscriber Service
echo [2/2] Starting MQTT Subscriber Service...
cd /d "%~dp0"
set PYTHONPATH=%CD%
start "MQTT Subscriber" "%~dp0venv\Scripts\python.exe" "%~dp0src\service_main.py"
timeout /t 5 /nobreak >nul
echo       [OK] Service started

echo.
echo ============================================
echo Services Started
echo ============================================
echo.
echo Check status:
echo   - Mosquitto: Task Manager ^> Mosquitto Broker
echo   - Subscriber: Task Manager ^> MQTT Subscriber
echo.
echo Logs: %~dp0logs\mqtt_subscriber.log
echo.
pause
