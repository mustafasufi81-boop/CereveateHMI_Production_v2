@echo off
REM ============================================================================
REM MQTT Subscriber Service - Stop Service
REM Run as Administrator
REM ============================================================================

echo Stopping MQTT Subscriber Service...
echo.

net stop MQTTSubscriberService
if %errorLevel% neq 0 (
    echo.
    echo ERROR: Failed to stop service
    echo Service may not be running or you need Administrator privileges
    echo.
    pause
    exit /b 1
)

echo.
echo Service stopped successfully!
echo.
pause
