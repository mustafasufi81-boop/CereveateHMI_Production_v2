@echo off
REM ============================================================================
REM Stop Production HMI System (Windows)
REM Stops nginx (Frontend) + Flask Backend (Waitress)
REM ============================================================================

echo ============================================================================
echo Stopping Production HMI System
echo ============================================================================
echo.

REM ============================================================================
REM STEP 1: Stop nginx
REM ============================================================================
echo [1/2] Stopping nginx...

tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
if %errorlevel% equ 0 (
    REM Try graceful shutdown first
    if exist "C:\nginx\nginx.exe" (
        C:\nginx\nginx.exe -s quit
        timeout /t 2 /nobreak >nul
    )
    
    REM Force kill if still running
    tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
    if %errorlevel% equ 0 (
        taskkill /F /IM nginx.exe >nul 2>&1
        echo [SUCCESS] nginx stopped
    ) else (
        echo [SUCCESS] nginx stopped gracefully
    )
) else (
    echo [INFO] nginx is not running
)

echo.

REM ============================================================================
REM STEP 2: Stop Flask Backend (Waitress)
REM ============================================================================
echo [2/2] Stopping Flask Backend (Waitress)...

REM Find processes listening on port 6001
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":6001"') do (
    set PID=%%a
)

if defined PID (
    taskkill /F /PID %PID% >nul 2>&1
    if %errorlevel% equ 0 (
        echo [SUCCESS] Flask Backend stopped (PID: %PID%)
    ) else (
        echo [WARNING] Could not stop process %PID%
    )
) else (
    echo [INFO] Flask Backend is not running on port 6001
)

REM Also stop any Python processes with "waitress" or "wsgi" in command line
echo.
echo Checking for remaining Python backend processes...
wmic process where "name='python.exe' and CommandLine like '%%waitress%%'" get ProcessId 2>nul | findstr /R "[0-9]" >nul 2>&1
if %errorlevel% equ 0 (
    for /f "skip=1" %%p in ('wmic process where "name='python.exe' and CommandLine like '%%waitress%%'" get ProcessId 2^>nul') do (
        taskkill /F /PID %%p >nul 2>&1
        echo [SUCCESS] Stopped Python process: %%p
    )
) else (
    echo [INFO] No remaining backend processes found
)

echo.
echo ============================================================================
echo Production HMI System Stopped
echo ============================================================================
echo.
pause
