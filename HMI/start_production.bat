@echo off
REM ============================================================================
REM Start Production HMI System (Windows)
REM Starts nginx (Frontend) + Flask Backend (Waitress)
REM ============================================================================

echo ============================================================================
echo Starting Production HMI System
echo ============================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Create logs directory if it doesn't exist
if not exist "logs\" mkdir logs

REM Check if nginx is installed
if not exist "C:\nginx\nginx.exe" (
    echo [WARNING] nginx not found at C:\nginx\
    echo Please install nginx or update the path in this script
    echo.
    echo Skipping nginx startup...
    set NGINX_INSTALLED=0
) else (
    set NGINX_INSTALLED=1
)

REM ============================================================================
REM STEP 1: Start Flask Backend (Waitress)
REM ============================================================================
echo [1/2] Starting Flask Backend (Waitress on port 6001)...
echo.

REM Check if backend is already running
netstat -ano | findstr ":6001" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARNING] Port 6001 is already in use!
    echo Flask backend may already be running.
    echo.
) else (
    REM Create a VBS script to run Flask backend silently in background
    echo Set WshShell = CreateObject("WScript.Shell") > "%TEMP%\start_flask_backend.vbs"
    echo WshShell.CurrentDirectory = "%~dp0" >> "%TEMP%\start_flask_backend.vbs"
    echo WshShell.Run "cmd /c venv\Scripts\activate.bat && waitress-serve --host=0.0.0.0 --port=6001 --threads=6 --channel-timeout=120 --connection-limit=1000 wsgi:application > logs\waitress.log 2>&1", 0, False >> "%TEMP%\start_flask_backend.vbs"
    
    REM Execute the VBS script to start backend silently
    cscript //nologo "%TEMP%\start_flask_backend.vbs"
    del "%TEMP%\start_flask_backend.vbs"
    
    REM Wait for backend to start
    timeout /t 5 /nobreak >nul
    
    netstat -ano | findstr ":6001" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [SUCCESS] Flask Backend started on port 6001 (background service)
    ) else (
        echo [ERROR] Failed to start Flask Backend!
        echo Check logs\waitress.log for errors
    )
)

echo.

REM ============================================================================
REM STEP 2: Start nginx (Frontend on port 8080)
REM ============================================================================
if %NGINX_INSTALLED% equ 1 (
    echo [2/2] Starting nginx (Frontend on port 8080)...
    echo.
    
    REM Check if nginx  silently in background
        cd /d C:\nginx
        start /B "" "C:\nginx\nginx.exe"
        cd /d "%~dp0"
        
        REM Wait for nginx to start
        timeout /t 2 /nobreak >nul
        
        tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
        if %errorlevel% equ 0 (
            echo [SUCCESS] nginx started on port 8080 (background service)
        REM Wait for nginx to start
        timeout /t 2 /nobreak >nul
        
        tasklist /FI "IMAGENAME eq nginx.exe" 2>NUL | find /I /N "nginx.exe">NUL
        if %errorlevel% equ 0 (
            echo [SUCCESS] nginx started on port 8080
        ) else (
            echo [ERROR] Failed to start nginx!
            echo Check C:\nginx\logs\error.log
        )
    )
) else (
    echo [2/2] nginx not installed - skipped
    echo.
    echo NOTE: Without nginx, access Flask directly at http://localhost:6001
)

echo.
echo ============================================================================
echo Production HMI System Status
echo ============================================================================
echo   Flask Backend:  http://localhost:6001
if %NGINX_INSTALLED% equ 1 (
    echo   nginx Frontend: http://localhost:8080
) else (
    echo   nginx Frontend: NOT INSTALLED
)
echo ============================================================================
echo.
echo To stop the system, run: stop_production.bat
echo.
pause
