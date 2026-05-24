@echo off
REM ========================================
REM API vs MQTT Comparison HMI Dashboard
REM Startup Script
REM ========================================

echo.
echo ========================================
echo   Comparison HMI Dashboard
echo   API vs MQTT Analysis
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

REM Stop any running comparison_app.py instances
echo [1/5] Stopping any running instances...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *comparison_app*" >NUL 2>&1
timeout /t 2 /nobreak >NUL

REM Kill process using port 5003
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5003') do (
    taskkill /F /PID %%a >NUL 2>&1
)
timeout /t 2 /nobreak >NUL
echo   Previous instances stopped.

echo [2/5] Checking dependencies...
pip install -q flask flask-socketio flask-cors psycopg2-binary requests eventlet
if errorlevel 1 (
    echo WARNING: Some dependencies may not be installed properly
)

echo [3/5] Checking OPC Server...
netstat -ano | findstr :5001 >nul
if errorlevel 0 (
    echo   ✓ OPC Server appears to be running on port 5001
) else (
    echo   WARNING: OPC Server may not be running on port 5001
    echo   The dashboard will work with database-only mode
)

echo [4/5] Starting Comparison HMI Dashboard...
echo.
echo ==========================================
echo   Dashboard URL: http://localhost:5003
echo ==========================================
echo   Data Sources:
echo   - API:  http://localhost:5001 (OPC Live)
echo   - MQTT: PostgreSQL Database
echo ==========================================
echo.
echo Press Ctrl+C to stop the server
echo.

python comparison_app.py

pause
