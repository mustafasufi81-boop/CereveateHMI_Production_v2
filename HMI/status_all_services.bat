@echo off
REM ============================================================================
REM Check Status of All HMI Services (Windows)
REM Checks: Nginx (Frontend Proxy) + Flask Backend (Waitress)
REM ============================================================================

echo ============================================================================
echo HMI Services Status Check
echo ============================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

set ALL_RUNNING=1

REM ============================================================================
REM CHECK 1: Flask Backend (Port 6001)
REM ============================================================================
echo [1/2] Flask Backend Status (Port 6001)
echo -----------------------------------------------

netstat -ano | findstr ":6001" >nul 2>&1
if %errorlevel% equ 0 (
    echo Status: [RUNNING]
    echo.
    echo Details:
    for /f "skip=4 tokens=2,5" %%a in ('netstat -ano ^| findstr ":6001"') do (
        echo   - Local Address: %%a
        echo   - Process ID: %%b
        goto :backend_done
    )
    :backend_done
    echo.
    
    REM Check if service is responding
    echo Testing backend connectivity...
    curl -s -o nul -w "HTTP Status: %%{http_code}\n" http://localhost:6001/api/system/health 2>nul
    if %errorlevel% neq 0 (
        echo [INFO] Backend is running but health check endpoint not responding
        echo        (This is normal if /api/system/health is not implemented)
    )
) else (
    echo Status: [STOPPED]
    echo.
    echo [WARNING] Flask backend is not running!
    set ALL_RUNNING=0
)

echo.

REM ============================================================================
REM CHECK 2: Nginx (Port 8080 & 8443)
REM ============================================================================
echo [2/2] Nginx Status (Ports 8080, 8443)
echo -----------------------------------------------

tasklist /FI "IMAGENAME eq nginx.exe" /FO LIST 2>NUL | find /I "nginx.exe">NUL
if %errorlevel% equ 0 (
    echo Status: [RUNNING]
    echo.
    echo Details:
    for /f "skip=3 tokens=2" %%a in ('tasklist /FI "IMAGENAME eq nginx.exe" /FO LIST ^| findstr "PID:"') do (
        echo   - Process ID: %%a
    )
    echo.
    
    REM Check HTTP port 8080
    netstat -ano | findstr ":8080" | findstr "LISTENING" >nul 2>&1
    if %errorlevel% equ 0 (
        echo   - HTTP Port 8080: [LISTENING]
    ) else (
        echo   - HTTP Port 8080: [NOT LISTENING]
    )
    
    REM Check HTTPS port 8443
    netstat -ano | findstr ":8443" | findstr "LISTENING" >nul 2>&1
    if %errorlevel% equ 0 (
        echo   - HTTPS Port 8443: [LISTENING]
    ) else (
        echo   - HTTPS Port 8443: [NOT LISTENING]
    )
    
    echo.
    
    REM Test nginx connectivity
    echo Testing nginx connectivity...
    curl -s -o nul -w "HTTP Status: %%{http_code}\n" http://localhost:8080 2>nul
    if %errorlevel% neq 0 (
        echo [INFO] Nginx is running but not responding on port 8080
    )
) else (
    echo Status: [STOPPED]
    echo.
    echo [WARNING] Nginx is not running!
    set ALL_RUNNING=0
)

echo.

REM ============================================================================
REM SUMMARY
REM ============================================================================
echo ============================================================================
echo Summary
echo ============================================================================
echo.

if %ALL_RUNNING%==1 (
    echo [SUCCESS] All services are running!
    echo.
    echo Access Points:
    echo   - HMI UI (HTTP):   http://localhost:8080
    echo   - HMI UI (HTTPS):  https://localhost:8443
    echo   - Backend API:     http://localhost:6001/api/
    echo.
    echo Service Management:
    echo   - Stop services:    stop_all_services.bat
    echo   - Restart:          restart_all_services.bat
    echo.
) else (
    echo [WARNING] Some services are not running!
    echo.
    echo To start all services: start_all_services.bat
    echo.
)

REM ============================================================================
REM ADDITIONAL DIAGNOSTICS
REM ============================================================================
echo ============================================================================
echo Recent Log Files
echo ============================================================================
echo.

if exist "logs\waitress.log" (
    echo Flask Backend Log (last 5 lines):
    echo -----------------------------------------------
    powershell -Command "Get-Content logs\waitress.log -Tail 5 -ErrorAction SilentlyContinue"
    echo.
) else (
    echo [INFO] No Flask backend log found: logs\waitress.log
    echo.
)

if exist "nginx-1.28.0\logs\error.log" (
    echo Nginx Error Log (last 5 lines):
    echo -----------------------------------------------
    powershell -Command "Get-Content nginx-1.28.0\logs\error.log -Tail 5 -ErrorAction SilentlyContinue"
    echo.
) else (
    echo [INFO] No Nginx error log found: nginx-1.28.0\logs\error.log
    echo.
)

echo ============================================================================
echo Status Check Complete
echo ============================================================================
