@echo off
REM ML Background Learning System Startup Script
REM Starts the system in background

echo ====================================================================
echo ML BACKGROUND LEARNING SYSTEM
echo ====================================================================
echo.

cd /d "%~dp0"

REM Check if virtual environment exists
if not exist "..\venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found!
    echo Please run: python -m venv ..\venv
    echo Then: ..\venv\Scripts\pip install -r ml_requirements.txt
    pause
    exit /b 1
)

REM Check if dependencies installed
echo Checking dependencies...
..\venv\Scripts\python.exe -c "import pandas, sklearn, yaml" 2>nul
if errorlevel 1 (
    echo ERROR: Dependencies not installed!
    echo Installing now...
    ..\venv\Scripts\pip.exe install -r ml_requirements.txt
    if errorlevel 1 (
        echo Installation failed!
        pause
        exit /b 1
    )
)

echo.
echo Dependencies: OK
echo.
echo Starting ML Background System...
echo Press Ctrl+C to stop
echo.
echo ====================================================================
echo.

REM Start the system
..\venv\Scripts\python.exe background_process_manager.py

if errorlevel 1 (
    echo.
    echo ====================================================================
    echo System stopped with errors!
    echo ====================================================================
    pause
    exit /b 1
)

echo.
echo ====================================================================
echo System stopped cleanly
echo ====================================================================
pause
