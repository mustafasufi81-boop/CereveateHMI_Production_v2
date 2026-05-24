@echo off
REM ============================================================================
REM MQTT Subscriber Service - Start Service
REM Run as Administrator
REM ============================================================================

echo Starting MQTT Subscriber Service...
echo.

net start MQTTSubscriberService
if %errorLevel% neq 0 (
    echo.
    echo ERROR: Failed to start service
    echo Make sure:
    echo   1. Service is installed (run install_service.bat)
    echo   2. Running as Administrator
    echo   3. PostgreSQL is running
    echo   4. MQTT broker is running
    echo.
    pause
    exit /b 1
)

echo.
echo Service started successfully!
echo.
echo To check status: sc query MQTTSubscriberService
echo To view logs: type logs\mqtt_subscriber.log
echo.
pause
