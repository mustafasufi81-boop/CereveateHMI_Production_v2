@echo off
REM ============================================================================
REM START CONTINUOUS IMPORTER SERVICE
REM Monitors directory for new files and processes automatically
REM ============================================================================

echo ========================================
echo CONTINUOUS IMPORTER SERVICE
echo Monitoring Mode
echo ========================================
echo.

cd /d "%~dp0"

REM Activate virtual environment if exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

echo Starting continuous service...
echo Press Ctrl+C to stop
echo.

python services\continuous_importer_service.py

echo.
echo Service stopped
pause
