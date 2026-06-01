@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Start C# OPC DA Backend (OpcDaWebBrowser.exe)
REM Main service for PLC/OPC connectivity
REM Listens on: http://0.0.0.0:5001
REM SignalR Hub: /opcHub
REM Connects to: PostgreSQL Automation_DB @ localhost:5432
REM ============================================================================

cd /d "%~dp0"

echo ============================================================
echo   Starting C# OPC DA Backend  ^|  Port: 5001
echo   Main PLC/OPC connectivity service
echo ============================================================
echo.

REM Check if already running
netstat -ano | findstr ":5001" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARNING] Port 5001 is already in use - OPC Backend may already be running.
    pause
    exit /b 0
)

REM Check if the published executable exists
if not exist "..\CSharpBackend\bin\Release\net8.0\publish\OpcDaWebBrowser.exe" (
    echo [ERROR] OpcDaWebBrowser.exe not found!
    echo Expected: d:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish\OpcDaWebBrowser.exe
    echo.
    echo Please build it first by running:
    echo   cd d:\CereveateHMI_Production\CSharpBackend
    echo   build.bat
    pause
    exit /b 1
)

REM Check PostgreSQL is accessible (warn only)
netstat -ano | findstr ":5432" | findstr "LISTENING" >nul 2>&1
if not %errorlevel% equ 0 (
    echo [WARNING] PostgreSQL does not appear to be running on port 5432.
    echo           OPC Backend needs it for historian ingest.
    echo           Start PostgreSQL first: net start postgresql
    echo           Continuing anyway...
    echo.
)

echo Starting OPC DA Backend...
echo.
start "OpcDaBackend" cmd /k "..\CSharpBackend\bin\Release\net8.0\publish\OpcDaWebBrowser.exe"

REM Wait and verify
echo Waiting for OPC Backend to start...
set /a RETRY=0
:wait_opc
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":5001" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo [SUCCESS] OPC DA Backend is running at http://localhost:5001
    echo           SignalR Hub: http://localhost:5001/opcHub
    echo.
    goto :end
)
set /a RETRY+=1
if !RETRY! lss 20 (
    echo   Waiting... !RETRY!/20
    goto :wait_opc
)

echo [ERROR] OPC DA Backend did not start within 20 seconds.
echo Check the console window for errors.

:end
pause
