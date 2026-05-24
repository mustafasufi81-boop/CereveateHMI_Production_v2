@echo off
REM ============================================================================
REM MQTT Subscriber Service - Windows Service Uninstaller
REM Run as Administrator
REM ============================================================================

echo ============================================================================
echo MQTT Subscriber Service - Windows Service Uninstallation
echo ============================================================================
echo.

REM Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

echo [1/3] Stopping service if running...
net stop MQTTSubscriberService >nul 2>&1
if %errorLevel% equ 0 (
    echo     Service stopped
) else (
    echo     Service was not running
)

echo.
echo [2/3] Uninstalling Windows Service...
python windows_service.py remove
if %errorLevel% neq 0 (
    echo ERROR: Service uninstallation failed
    pause
    exit /b 1
)
echo     Service uninstalled successfully

echo.
echo [3/3] Cleanup complete
echo.
echo ============================================================================
echo Uninstallation Complete!
echo ============================================================================
echo.
echo The MQTT Subscriber Service has been removed from Windows Services.
echo.
echo Note: Configuration files and logs have been preserved.
echo To completely remove the service, delete the entire folder.
echo.
pause
