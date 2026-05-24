@echo off
REM ============================================================================
REM HMI Flask Application - Windows Production Deployment Script
REM Deploys using Waitress WSGI server
REM ============================================================================

echo ============================================================================
echo HMI Flask Application - Production Deployment (Windows)
echo ============================================================================
echo.

REM Change to script directory
cd /d "%~dp0"

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.8+ and add to PATH
    pause
    exit /b 1
)

echo [1/7] Checking Python version...
python --version

REM Check if virtual environment exists
if not exist "venv\" (
    echo [2/7] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment!
        pause
        exit /b 1
    )
) else (
    echo [2/7] Virtual environment already exists
)

REM Activate virtual environment
echo [3/7] Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment!
    pause
    exit /b 1
)

REM Upgrade pip
echo [4/7] Upgrading pip...
python -m pip install --upgrade pip

REM Install production requirements
echo [5/7] Installing production dependencies...
pip install -r requirements-production.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies!
    pause
    exit /b 1
)

REM Check if .env file exists
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo Creating from .env.example...
    copy .env.example .env
    echo.
    echo [ACTION REQUIRED] Please edit .env file with your production settings!
    echo Press any key to open .env file in notepad...
    pause >nul
    notepad .env
)

REM Create logs directory
if not exist "logs\" mkdir logs

REM Set environment to production
set HMI_ENV=production

echo [6/7] Validating configuration...
python config_manager.py
if errorlevel 1 (
    echo [ERROR] Configuration validation failed!
    echo Please fix configuration errors in .env file
    pause
    exit /b 1
)

echo [7/7] Starting HMI Flask Application with Waitress...
echo.
echo ============================================================================
echo Server will start on: http://0.0.0.0:6001
echo Press CTRL+C to stop the server
echo ============================================================================
echo.

REM Start with Waitress
waitress-serve --host=0.0.0.0 --port=8080 --threads=6 --channel-timeout=120 --connection-limit=1000 wsgi:application

REM If server stops
echo.
echo ============================================================================
echo Server stopped
echo ============================================================================
pause
