@echo off
REM ============================================================================
REM Stop Flask HMI Backend (kills process listening on port 6001)
REM ============================================================================

echo Stopping Flask HMI Backend (port 6001)...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":6001" ^| findstr "LISTENING"') do (
    echo Killing PID %%a
    taskkill /PID %%a /F >nul 2>&1
)

netstat -ano | findstr ":6001" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [ERROR] Could not stop Flask on port 6001.
) else (
    echo [SUCCESS] Flask HMI Backend stopped.
)
pause
