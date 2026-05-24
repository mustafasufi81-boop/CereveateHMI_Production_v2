@echo off
REM ============================================================================
REM Check Production HMI System Status (Windows)
REM Shows status of nginx (Frontend) + Flask Backend (Waitress)
REM ============================================================================

echo ============================================================================
echo Production HMI System Status
echo (All services running as background processes)
echo ============================================================================
echo.

REM ============================================================================
REM Check nginx Status
REM ============================================================================
echo [1/3] nginx Status (Frontend - Port 8080)
echo ----------------------------------------

tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
if %errorlevel% equ 0 (
    echo Status: RUNNING
    for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq nginx.exe" /NH') do (
        echo PID: %%a
    )
    echo URL: http://localhost:8080
) else (
    echo Status: NOT RUNNING
)

echo.

REM ============================================================================
REM Check Flask Backend Status
REM ============================================================================
echo [2/3] Flask Backend Status (Waitress - Port 6001)
echo ----------------------------------------

netstat -ano | findstr ":6001" >nul 2>&1
if %errorlevel% equ 0 (
    echo Status: RUNNING
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":6001" ^| findstr "LISTENING"') do (
        echo PID: %%a
    )
    echo URL: http://localhost:6001
) else (
    echo Status: NOT RUNNING
)

echo.

REM ============================================================================
REM Check Active Connections
REM ============================================================================
echo [3/3] Active Connections
echo ----------------------------------------

REM nginx connections (port 8080)
for /f "tokens=*" %%a in ('netstat -ano ^| findstr ":8080" ^| find /C ":8080"') do (
    echo nginx connections: %%a
)

REM Backend connections (port 6001)
for /f "tokens=*" %%a in ('netstat -ano ^| findstr ":6001" ^| find /C ":6001"') do (
    echo Backend connections: %%a
)

echo.

REM ============================================================================
REM Recent Logs
REM ============================================================================
echo [Logs]
echo ----------------------------------------
if exist "logs\waitress.log" (
    echo Flask Backend Log: logs\waitress.log
    echo Last 5 lines:
    powershell -Command "Get-Content logs\waitress.log -Tail 5 -ErrorAction SilentlyContinue"
)
if exist "logs\hmi_app.log" (
    echo Flask App Log: logs\hmi_app.log
)
if exist "C:\nginx\logs\error.log" (
    echo nginx Error Log: C:\nginx\logs\error.log
)
if exist "C:\nginx\logs\access.log" (
    echo nginx Access Log: C:\nginx\logs\access.log
)

echo.
echo ============================================================================
echo To start system: start_production.bat
echo To stop system:  stop_production.bat
echo ============================================================================
echo.
pause
