@echo off
echo ========================================
echo   HMI Dashboard - Starting Services
echo ========================================
echo.
echo INFO: HMI works in 3 modes:
echo   - FULL: Live + Historical (requires C# backend + Database)
echo   - HISTORICAL: Historical only (requires Database)
echo   - DEMO: UI exploration (no requirements)
echo.
echo HMI will start regardless of what's connected!
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    pause
    exit /b 1
)

echo [1/2] Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo [2/2] Starting HMI Flask application...
echo.
echo ==========================================
echo   HMI Dashboard Access:
echo   - Local:       http://localhost:5002
echo   - Network:     http://192.168.0.120:5002
echo ==========================================
echo   Optional connections:
echo   - C# Backend:  http://localhost:5000 (for live data)
echo   - Database:    PostgreSQL historian (for historical trends)
echo ==========================================
echo.
echo NOTE: If remote access fails, run ADD_FIREWALL_RULE.bat as Administrator
echo.
echo Press Ctrl+C to stop the server
echo.

python app.py

pause
