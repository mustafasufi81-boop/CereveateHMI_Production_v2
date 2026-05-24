@echo off
echo ========================================
echo PostgreSQL Logger Setup
echo ========================================
echo.

cd /d "%~dp0"

REM Check if virtual environment exists
if exist "venv\" (
    echo Virtual environment already exists.
    choice /C YN /M "Do you want to recreate it"
    if errorlevel 2 goto :INSTALL
    echo Removing old virtual environment...
    rmdir /s /q venv
)

:CREATE_VENV
echo.
echo Creating virtual environment...
python -m venv venv

if errorlevel 1 (
    echo.
    echo ERROR: Failed to create virtual environment
    echo Make sure Python is installed and in PATH
    pause
    exit /b 1
)

:INSTALL
echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo To run the server:
echo   1. Run start_server.bat
echo   2. Open browser: http://localhost:8001
echo.
pause
