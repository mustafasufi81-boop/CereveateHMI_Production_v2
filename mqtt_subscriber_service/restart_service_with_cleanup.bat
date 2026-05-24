@echo off
REM ============================================================================
REM MQTT Subscriber Service - Complete Restart with Cache Cleanup
REM ============================================================================

echo ============================================================================
echo MQTT Subscriber Service - Complete Restart
echo ============================================================================
echo.

REM Step 1: Stop the service
echo [1/4] Stopping MQTT Subscriber Service...
sc stop MQTTSubscriberService
timeout /t 3 /nobreak >nul
echo       [OK] Service stop command sent
echo.

REM Step 2: Clean Python cache
echo [2/4] Cleaning Python bytecode cache...
cd /d "%~dp0"
for /d /r %%d in (__pycache__) do (
    if exist "%%d" (
        echo       Removing: %%d
        rd /s /q "%%d" 2>nul
    )
)
del /s /q *.pyc 2>nul
echo       [OK] Cache cleaned
echo.

REM Step 3: Wait for complete shutdown
echo [3/4] Waiting for process to fully terminate...
timeout /t 5 /nobreak >nul
echo       [OK] Waited 5 seconds
echo.

REM Step 4: Start the service
echo [4/4] Starting MQTT Subscriber Service...
sc start MQTTSubscriberService
timeout /t 3 /nobreak >nul
echo       [OK] Service start command sent
echo.

REM Check service status
echo ============================================================================
echo Service Status:
sc query MQTTSubscriberService | findstr "STATE"
echo.

echo ============================================================================
echo Restart Complete!
echo.
echo Wait 5-10 seconds for the service to fully initialize.
echo Check logs at: logs\mqtt_subscriber.log
echo ============================================================================
pause
