@echo off
REM MQTT Subscriber Service - Startup Script
REM Runs the MQTT Subscriber Service in console mode

echo ========================================
echo MQTT Subscriber Service
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv\" (
    echo Virtual environment not found. Creating...
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/update dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet

REM Run the service
echo.
echo Starting MQTT Subscriber Service...
echo.
set PYTHONPATH=%CD%
python src/service_main.py

REM Deactivate virtual environment
deactivate

pause
