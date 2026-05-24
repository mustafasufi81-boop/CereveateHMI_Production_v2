@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM MQTT Services Manager - Start/Stop/Restart Services
REM ** MUST RUN AS ADMINISTRATOR **
REM ============================================================================

REM Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ============================================================================
    echo ERROR: This script requires Administrator privileges
    echo ============================================================================
    echo.
    echo Please right-click this file and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

REM Check command line argument
set ACTION=%1
if "%ACTION%"=="" set ACTION=menu

if /I "%ACTION%"=="start" goto START
if /I "%ACTION%"=="stop" goto STOP
if /I "%ACTION%"=="restart" goto RESTART
if /I "%ACTION%"=="status" goto STATUS
if /I "%ACTION%"=="menu" goto MENU

echo Invalid option: %ACTION%
echo Usage: mqtt_services.bat [start^|stop^|restart^|status]
pause
exit /b 1

:MENU
cls
echo ============================================================================
echo            MQTT Services Manager
echo ============================================================================
echo.
echo   1. Start Services
echo   2. Stop Services
echo   3. Restart Services
echo   4. Check Status
echo   5. Exit
echo.
echo ============================================================================
set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" goto START
if "%choice%"=="2" goto STOP
if "%choice%"=="3" goto RESTART
if "%choice%"=="4" goto STATUS
if "%choice%"=="5" exit /b 0
echo Invalid choice!
timeout /t 2 /nobreak >nul
goto MENU

:START
cls
echo ============================================================================
echo Starting MQTT Services
echo ============================================================================
echo.

echo [1/3] Stopping any existing MQTT Subscriber Service instances...
taskkill /F /IM python.exe /FI "COMMANDLINE eq *service_main.py*" 2>nul
timeout /t 2 /nobreak >nul
echo       [OK] Cleaned up existing service instances

echo.
echo [2/3] Starting Mosquitto Broker in background...
netstat -ano | findstr ":1883" >nul
if %errorlevel% == 0 (
    echo       [!] Port 1883 already in use - Stopping existing Mosquitto...
    taskkill /F /IM mosquitto.exe /T 2>nul
    timeout /t 3 /nobreak >nul
    echo       [OK] Existing Mosquitto stopped
)

cscript //nologo "%~dp0run_mosquitto_background.vbs"
timeout /t 3 /nobreak >nul
netstat -ano | findstr ":1883" >nul
if %errorlevel% == 0 (
    echo       [OK] Mosquitto started in background on port 1883
) else (
    echo       [ERROR] Mosquitto failed to start
    pause
    goto MENU
)

echo.
echo [3/3] Starting MQTT Subscriber Service in background...
cscript //nologo "%~dp0run_service_background.vbs"
timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq *service*" 2>nul | findstr "python" >nul
if %errorlevel% == 0 (
    echo       [OK] MQTT Subscriber Service started in background
) else (
    echo       [!] Warning: Could not verify service started
)

echo.
echo ============================================================================
echo Services Started Successfully
echo ============================================================================
echo.
echo Mosquitto Broker:     Running in background on port 1883
echo Subscriber Service:   Running in background (hidden)
echo.
echo Logs: %~dp0logs\mqtt_subscriber.log
echo.
if "%ACTION%"=="menu" (
    pause
    goto MENU
)
exit /b 0

:STOP
cls
echo ============================================================================
echo Stopping MQTT Services
echo ============================================================================
echo.

echo [1/2] Stopping all MQTT Subscriber Service instances...
taskkill /F /IM python.exe /FI "COMMANDLINE eq *service_main.py*" 2>nul
if %errorlevel% == 0 (
    echo       [OK] MQTT Subscriber Service stopped
    timeout /t 2 /nobreak >nul
) else (
    echo       [!] No subscriber service found
)

echo.
echo [2/2] Stopping all Mosquitto Broker instances...
taskkill /F /IM mosquitto.exe /T 2>nul
if %errorlevel% == 0 (
    echo       [OK] Mosquitto Broker stopped
    timeout /t 2 /nobreak >nul
) else (
    echo       [!] No Mosquitto processes found
)

echo.
echo ============================================================================
echo Services Stopped
echo ============================================================================
echo.
if "%ACTION%"=="menu" (
    pause
    goto MENU
)
exit /b 0

:RESTART
echo ============================================================================
echo Restarting MQTT Services
echo ============================================================================
echo.
call :STOP
timeout /t 2 /nobreak >nul
call :START
if "%ACTION%"=="menu" (
    pause
    goto MENU
)
exit /b 0

:STATUS
cls
echo ============================================================================
echo MQTT Services Status
echo ============================================================================
echo.

echo Mosquitto Broker:
tasklist /FI "IMAGENAME eq mosquitto.exe" 2>nul | findstr "mosquitto" >nul
if %errorlevel% == 0 (
    echo   [OK] Running
    netstat -ano | findstr ":1883" | findstr "LISTENING"
) else (
    echo   [X] Not Running
)

echo.
echo MQTT Subscriber Service:
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH 2^>nul ^| findstr "python"') do (
    set "found=1"
    wmic process where "ProcessId=%%~a" get CommandLine 2>nul | findstr /I "service_main.py" >nul
    if !errorlevel! == 0 (
        echo   [OK] Running - PID: %%~a
    )
)
if not defined found (
    echo   [X] Not Running
)

echo.
echo Log File:
if exist "%~dp0logs\mqtt_subscriber.log" (
    echo   [OK] %~dp0logs\mqtt_subscriber.log
    echo.
    echo Last 5 log entries:
    powershell -command "Get-Content '%~dp0logs\mqtt_subscriber.log' -Tail 5"
) else (
    echo   [!] Log file not found
)

echo.
echo ============================================================================
if "%ACTION%"=="menu" (
    pause
    goto MENU
)
exit /b 0
