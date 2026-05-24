@echo off
REM ============================================================================
REM Restart Production HMI System (Windows)
REM Stops and restarts nginx + Flask Backend
REM ============================================================================

echo ============================================================================
echo Restarting Production HMI System
echo ============================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

echo Stopping services...
call stop_production.bat

echo.
echo Waiting 3 seconds...
timeout /t 3 /nobreak >nul

echo.
echo Starting services...
call start_production.bat
