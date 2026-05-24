@echo off
REM ============================================================================
REM HMI Flask Application - Windows Development/Testing Script
REM Starts the app in development mode for local testing
REM ============================================================================

echo ============================================================================
echo HMI Flask Application - Development Server
echo ============================================================================
echo.

cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo Installing dependencies...
pip install -r requirements.txt --upgrade

REM Set environment to development
set HMI_ENV=development
set DEBUG=True

REM Create .env if not exists
if not exist ".env" (
    copy .env.example .env
)

REM Create logs directory
if not exist "logs\" mkdir logs

echo.
echo ============================================================================
echo Starting Development Server on http://localhost:6001
echo Press CTRL+C to stop
echo ============================================================================
echo.

REM Start in development mode using original app.py
python app.py

pause
