@echo off
echo ========================================
echo Cereveate_Praxis OPC Server
echo Windows Service Installer
echo ========================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Administrator rights required!
    echo Please right-click this file and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

set SERVICE_NAME=CereveateOPCServer
set EXE_PATH=%~dp0OpcDaWebBrowser.exe

echo Installing Windows Service...
echo Service Name: %SERVICE_NAME%
echo Executable: %EXE_PATH%
echo.

REM Stop service if already running
sc query %SERVICE_NAME% >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Stopping existing service...
    sc stop %SERVICE_NAME%
    timeout /t 3 /nobreak >nul
    
    echo Removing existing service...
    sc delete %SERVICE_NAME%
    timeout /t 2 /nobreak >nul
)

REM Create service
sc create %SERVICE_NAME% binPath= "%EXE_PATH%" start= auto DisplayName= "Cereveate_Praxis OPC Server"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to create service!
    pause
    exit /b 1
)

REM Set service description
sc description %SERVICE_NAME% "Professional OPC DA Server with Web Interface - Cereveate_Praxis"

REM Configure recovery options (restart on failure)
sc failure %SERVICE_NAME% reset= 86400 actions= restart/3000/restart/3000/restart/3000

REM Start service
echo.
echo Starting service...
sc start %SERVICE_NAME%

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo SERVICE INSTALLED SUCCESSFULLY!
    echo ========================================
    echo.
    echo Service Name: %SERVICE_NAME%
    echo Status: Running
    echo Start Type: Automatic
    echo.
    echo Access the web interface at:
    echo http://localhost:5000
    echo.
    echo The service will:
    echo - Start automatically on system boot
    echo - Restart automatically on failure
    echo - Run silently in the background
    echo - Log to: Logs\app-YYYYMMDD.log
    echo.
) else (
    echo.
    echo WARNING: Service created but failed to start!
    echo Check logs for details: Logs\app-YYYYMMDD.log
    echo.
)

pause
