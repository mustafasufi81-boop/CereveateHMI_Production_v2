@echo off
echo ============================================================
echo  Starting ALL Cereveate HMI Services
echo ============================================================
echo.

REM ── Step 1: Verify PostgreSQL ──────────────────────────────
echo [1/5] Checking PostgreSQL...
sc query postgresql-x64-17 | findstr "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo     Starting PostgreSQL...
    net start postgresql-x64-17 >nul 2>&1
) else (
    echo     PostgreSQL already running. OK
)

REM ── Step 2: Verify Mosquitto ───────────────────────────────
echo [2/5] Checking Mosquitto...
sc query mosquitto | findstr "RUNNING" >nul 2>&1
if %errorlevel% neq 0 (
    echo     Starting Mosquitto...
    net start mosquitto >nul 2>&1
) else (
    echo     Mosquitto already running. OK
)

REM ── Step 3: Start OPC C# Backend ──────────────────────────
echo [3/5] Starting OPC Backend (port 5001)...
start "OPC Backend" /D "D:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\publish" OpcDaWebBrowser.exe
timeout /t 4 /nobreak >nul
echo     Done.

REM ── Step 4: Start MQTT Subscriber ─────────────────────────
echo [4/5] Starting MQTT Subscriber...
start "MQTT Subscriber" cmd /k "cd /d D:\CereveateHMI_Production\mqtt_subscriber_service && venv\Scripts\activate && set PYTHONPATH=D:\CereveateHMI_Production\mqtt_subscriber_service && python src\service_main.py"
timeout /t 3 /nobreak >nul
echo     Done.

REM ── Step 5: Start Flask HMI ───────────────────────────────
echo [5/5] Starting Flask HMI (port 6001)...
start "Flask HMI" cmd /k "cd /d D:\CereveateHMI_Production\HMI && .venv\Scripts\activate && python app.py"
timeout /t 8 /nobreak >nul
echo     Done.

REM ── Step 6: Start Nginx ───────────────────────────────────
echo [6/6] Starting Nginx (port 8090)...
start /D "D:\CereveateHMI_Production\HMI\nginx-1.28.0" /B nginx.exe
timeout /t 2 /nobreak >nul
echo     Done.

echo.
echo ============================================================
echo  All services started!
echo.
echo  Ports:  1883=Mosquitto  5001=OPC  6001=Flask  8090=Nginx
echo  HMI:    http://localhost:8090
echo ============================================================
pause
