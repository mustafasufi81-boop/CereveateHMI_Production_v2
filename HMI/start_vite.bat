@echo off
setlocal enabledelayedexpansion
REM ============================================================================
REM Start Vite React Frontend (apex-hmi)
REM Dev server: http://localhost:8090
REM Proxies /api  -> Flask http://localhost:6001
REM Proxies /api/opc, /api/plc, /opcHub -> C# OPC http://localhost:5001
REM ============================================================================

cd /d "%~dp0\apex-hmi"

echo ============================================================
echo   Starting Vite React Frontend  ^|  Port: 8090
echo ============================================================
echo.

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed or not in PATH.
    echo Please install Node.js from https://nodejs.org/
    pause
    exit /b 1
)

REM Check if npm packages are installed
if not exist "node_modules\" (
    echo [INFO] node_modules not found. Installing npm packages...
    npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed!
        pause
        exit /b 1
    )
)

REM Check if port 8090 is already in use
netstat -ano | findstr ":8090" | findstr "LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARNING] Port 8090 is already in use - Vite may already be running.
    pause
    exit /b 0
)

REM Check Flask backend is up (recommended before starting Vite)
netstat -ano | findstr ":6001" | findstr "LISTENING" >nul 2>&1
if not %errorlevel% equ 0 (
    echo [WARNING] Flask backend is NOT running on port 6001.
    echo           API calls will fail. Start start_flask.bat first.
    echo           Continuing anyway...
    echo.
)

echo Starting Vite dev server...
echo.
echo ============================================================
echo   Vite React Frontend: http://localhost:8090
echo   Proxied APIs:
echo     /api         -> http://localhost:6001  (Flask HMI)
echo     /api/opc     -> http://localhost:5001  (C# OPC Backend)
echo     /socket.io   -> http://localhost:6001  (WebSocket)
echo ============================================================
echo.
start "Vite React Frontend" cmd /k "npm run dev"

echo [INFO] Vite dev server window opened.
echo.
pause
