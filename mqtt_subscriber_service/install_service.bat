@echo off
REM ============================================================================
REM MQTT Subscriber Service - Windows Service Installer
REM Run as Administrator
REM ============================================================================

echo ============================================================================
echo MQTT Subscriber Service - Windows Service Installation
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

echo [1/5] Checking Python installation...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10+ and add to PATH
    pause
    exit /b 1
)
echo     Python found

echo.
echo [2/5] Checking required packages...
python -c "import win32serviceutil" >nul 2>&1
if %errorLevel% neq 0 (
    echo     Installing pywin32...
    pip install pywin32
    if %errorLevel% neq 0 (
        echo ERROR: Failed to install pywin32
        pause
        exit /b 1
    )
    
    REM Run pywin32 post-install
    python -c "import win32api; import sys; import os; sys.path.append(os.path.dirname(win32api.__file__)); import pywin32_postinstall; pywin32_postinstall.install()"
)
echo     All packages available

echo.
echo [3/5] Installing service dependencies...
pip install -r requirements.txt
if %errorLevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo     Dependencies installed

echo.
echo [4/5] Creating logs directory...
if not exist "logs" mkdir logs
echo     Logs directory ready

echo.
echo [5/5] Installing Windows Service...
python windows_service.py install
if %errorLevel% neq 0 (
    echo ERROR: Service installation failed
    pause
    exit /b 1
)
echo     Service installed successfully

echo.
echo ============================================================================
echo Installation Complete!
echo ============================================================================
echo.
echo Service Name: MQTTSubscriberService
echo Display Name: MQTT Subscriber Service
echo.
echo To start the service, run one of:
echo   1. net start MQTTSubscriberService
echo   2. sc start MQTTSubscriberService
echo   3. services.msc (and start manually)
echo.
echo Configuration: config\service_config.yaml
echo Logs: logs\mqtt_subscriber.log
echo.
echo To uninstall: run uninstall_service.bat
echo ============================================================================
echo.
pause
