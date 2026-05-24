@echo off
REM ============================================================================
REM Restart All HMI Services (Windows)
REM Stops and restarts: Nginx + Flask Backend
REM ============================================================================

echo ============================================================================
echo Restarting All HMI Services
echo ============================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM ============================================================================
REM STEP 1: Stop All Services
REM ============================================================================
echo [STEP 1] Stopping all services...
echo.
call stop_all_services.bat

if %errorlevel% neq 0 (
    echo.
    echo [WARNING] Some services may not have stopped cleanly
    echo Continuing with restart...
)

echo.
echo ============================================================================
echo Waiting 5 seconds before restart...
echo ============================================================================
timeout /t 5 /nobreak >nul

echo.

REM ============================================================================
REM STEP 2: Start All Services
REM ============================================================================
echo [STEP 2] Starting all services...
echo.
call start_all_services.bat

if %errorlevel% neq 0 (
    echo.
    echo ============================================================================
    echo ERROR: Failed to start services after restart
    echo ============================================================================
    echo.
    echo Troubleshooting steps:
    echo   1. Check if ports 6001, 8080, 8443 are free
    echo   2. Review logs: logs\waitress.log and nginx-1.28.0\logs\error.log
    echo   3. Try running stop_all_services.bat again
    echo   4. Restart your computer if issues persist
    echo.
    exit /b 1
)

echo.
echo ============================================================================
echo Restart Complete
echo ============================================================================
echo.
echo All services have been restarted successfully!
echo Check status with: status_all_services.bat
echo.
