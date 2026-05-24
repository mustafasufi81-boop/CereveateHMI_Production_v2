@echo off
echo ========================================
echo Starting WebSocket Bridge for HMI Live Data
echo ========================================
echo.

cd /d "%~dp0"

REM Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo ERROR: Virtual environment not found at venv\Scripts\activate.bat
    pause
    exit /b 1
)

REM Check if Flask-SocketIO is installed
python -c "import flask_socketio" 2>NUL
if errorlevel 1 (
    echo Installing Flask-SocketIO...
    pip install flask-socketio python-socketio flask-cors
)

echo.
echo Starting WebSocket Bridge on port 6001...
echo Press Ctrl+C to stop
echo.

python websocket_bridge.py

pause
