@echo off
echo ========================================
echo Cereveate_Praxis OPC Server
echo Auto-Start Installation (Task Scheduler)
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

set TASK_NAME=CereveateOPCServer
set EXE_PATH=%~dp0OpcDaWebBrowser.exe

echo Installing Auto-Start Task...
echo Task Name: %TASK_NAME%
echo Executable: %EXE_PATH%
echo.

REM Delete existing task if it exists
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Removing existing task...
    schtasks /delete /tn "%TASK_NAME%" /f
)

REM Create scheduled task to run at system startup
echo Creating auto-start task...
schtasks /create /tn "%TASK_NAME%" /tr "%EXE_PATH%" /sc onstart /ru SYSTEM /rl highest /f

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to create auto-start task!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Installation Complete!
echo ========================================
echo.
echo The OPC Server will now start automatically when Windows boots.
echo.
echo To start now, run: schtasks /run /tn "%TASK_NAME%"
echo To stop, use Task Manager or: taskkill /f /im OpcDaWebBrowser.exe
echo.
echo Access the web interface at: http://localhost:6001
echo.
pause
