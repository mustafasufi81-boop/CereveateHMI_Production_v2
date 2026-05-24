@echo off
REM ============================================================================
REM HMI Flask Application - Windows Service Installation Script
REM Requires: NSSM (Non-Sucking Service Manager)
REM Run as Administrator!
REM ============================================================================

echo ============================================================================
echo HMI Flask Application - Windows Service Installer
echo ============================================================================
echo.

REM Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script must be run as Administrator!
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

REM Configuration
set SERVICE_NAME=HMI_Flask_Service
set NSSM_PATH=C:\Tools\nssm\nssm.exe
set HMI_PATH=%~dp0
set PYTHON_EXE=%HMI_PATH%venv\Scripts\python.exe
set LOG_PATH=%HMI_PATH%logs

REM Check if NSSM exists
if not exist "%NSSM_PATH%" (
    echo [ERROR] NSSM not found at %NSSM_PATH%
    echo.
    echo Download NSSM from: https://nssm.cc/download
    echo Extract nssm.exe to C:\Tools\nssm\ or update NSSM_PATH in this script
    pause
    exit /b 1
)

REM Check if Python virtual environment exists
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python virtual environment not found!
    echo Please run deploy_windows.bat first to create virtual environment
    pause
    exit /b 1
)

REM Create logs directory
if not exist "%LOG_PATH%" mkdir "%LOG_PATH%"

REM Check if service already exists
sc query %SERVICE_NAME% >nul 2>&1
if %errorLevel% equ 0 (
    echo [INFO] Service already exists. Stopping and removing...
    "%NSSM_PATH%" stop %SERVICE_NAME%
    timeout /t 2 >nul
    "%NSSM_PATH%" remove %SERVICE_NAME% confirm
    timeout /t 2 >nul
)

REM Install service
echo [1/3] Installing HMI Flask Service...
"%NSSM_PATH%" install %SERVICE_NAME% "%PYTHON_EXE%" -m waitress --host=0.0.0.0 --port=6001 --threads=6 wsgi:application

REM Configure service
echo [2/3] Configuring service...
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "HMI Flask Application Service"
"%NSSM_PATH%" set %SERVICE_NAME% Description "Industrial HMI Flask Application with Real-Time Data Streaming"
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%HMI_PATH%"
"%NSSM_PATH%" set %SERVICE_NAME% AppEnvironmentExtra "HMI_ENV=production" "PYTHONPATH=%HMI_PATH%"
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%LOG_PATH%\service-stdout.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStderr "%LOG_PATH%\service-stderr.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateFiles 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateOnline 1
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateSeconds 86400
"%NSSM_PATH%" set %SERVICE_NAME% AppRotateBytes 10485760
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_PATH%" set %SERVICE_NAME% AppExit Default Restart
"%NSSM_PATH%" set %SERVICE_NAME% AppRestartDelay 60000

REM Start service
echo [3/3] Starting service...
net start %SERVICE_NAME%

echo.
echo ============================================================================
echo Service installed and started successfully!
echo ============================================================================
echo.
echo Service Name: %SERVICE_NAME%
echo Display Name: HMI Flask Application Service
echo.
echo Management Commands:
echo   Start:   net start %SERVICE_NAME%
echo   Stop:    net stop %SERVICE_NAME%
echo   Restart: net stop %SERVICE_NAME% ^&^& net start %SERVICE_NAME%
echo   Status:  sc query %SERVICE_NAME%
echo   Remove:  "%NSSM_PATH%" remove %SERVICE_NAME% confirm
echo.
echo Logs Location: %LOG_PATH%
echo ============================================================================
pause
