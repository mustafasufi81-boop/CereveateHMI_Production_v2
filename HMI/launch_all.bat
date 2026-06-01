@echo off
REM ============================================================================
REM Launch ALL HMI Services - Correct Startup Sequence
REM
REM  SEQUENCE:
REM  [PRE]  PostgreSQL must already be running  (net start postgresql)
REM  [PRE]  MQTT Broker must already be running (net start mosquitto)
REM
REM  1. C# OPC DA Backend  (port 5001) - PLC/OPC connectivity
REM  2. MQTT Real-Time Publisher        - DB -> MQTT broker
REM  3. Flask HMI Backend  (port 6001) - Main web app
REM  4. Nginx Proxy        (port 8080/8443)
REM  5. Vite React Frontend(port 8090) - Dev UI
REM  6. MQTT HMI Dashboard (optional)
REM
REM Each service opens in its own window for independent monitoring.
REM ============================================================================

cd /d "%~dp0"

echo ============================================================
echo   Launching All HMI Services (Full Stack)
echo ============================================================
echo.

REM ── Pre-flight: check PostgreSQL ──────────────────────────────
netstat -ano | findstr ":5432" | findstr "LISTENING" >nul 2>&1
if not %errorlevel% equ 0 (
    echo [ERROR] PostgreSQL is NOT running on port 5432!
    echo         Start it first:  net start postgresql
    echo         Then re-run this script.
    pause
    exit /b 1
)
echo [OK] PostgreSQL is running on port 5432

REM ── Pre-flight: check MQTT Broker ─────────────────────────────
netstat -ano | findstr ":1883" | findstr "LISTENING" >nul 2>&1
if not %errorlevel% equ 0 (
    echo [WARNING] MQTT Broker is NOT running on port 1883.
    echo           Start it:  net start mosquitto
    echo           Continuing - MQTT features will be unavailable.
    echo.
) else (
    echo [OK] MQTT Broker is running on port 1883
)

echo.
echo Each service will open in its own window.
echo.

REM ── Step 1: C# OPC DA Backend ─────────────────────────────────
echo [1/6] Starting C# OPC DA Backend (port 5001)...
start "OPC DA Backend" cmd /c "%~dp0start_opc_backend.bat"
timeout /t 5 /nobreak >nul

REM ── Step 2: MQTT Publisher ────────────────────────────────────
echo [2/6] Starting MQTT Real-Time Publisher...
start "MQTT Publisher" cmd /c "%~dp0start_mqtt_publisher.bat"
timeout /t 3 /nobreak >nul

REM ── Step 3: Flask HMI Backend ─────────────────────────────────
echo [3/6] Starting Flask HMI Backend (port 6001)...
start "Flask HMI Backend" cmd /c "%~dp0start_flask.bat"
timeout /t 8 /nobreak >nul

REM ── Step 4: Nginx Proxy ───────────────────────────────────────
echo [4/6] Starting Nginx Proxy (port 8080/8443)...
start "Nginx Proxy" cmd /c "%~dp0start_nginx.bat"
timeout /t 3 /nobreak >nul

REM ── Step 5: Vite React Frontend ───────────────────────────────
echo [5/6] Starting Vite React Frontend (port 8090)...
start "Vite Frontend" cmd /c "%~dp0start_vite.bat"
timeout /t 3 /nobreak >nul

REM ── Step 6: MQTT Dashboard (optional) ────────────────────────
echo [6/6] Starting MQTT HMI Dashboard (optional)...
start "MQTT Dashboard" cmd /c "%~dp0start_mqtt_app.bat"

echo.
echo ============================================================
echo   All services launched!
echo ============================================================
echo.
echo   OPC DA Backend:   http://localhost:5001   (PLC/OPC + SignalR)
echo   Flask HMI:        http://localhost:6001   (Main API)
echo   Nginx HTTP:       http://localhost:8080   (Proxy)
echo   Nginx HTTPS:      https://localhost:8443  (Proxy SSL)
echo   Vite Frontend:    http://localhost:8090   (React Dev UI)
echo   MQTT Dashboard:   Check its own console window
echo.
echo To stop services:
echo   stop_flask.bat   - Stop Flask
echo   stop_nginx.bat   - Stop Nginx
echo.
pause
