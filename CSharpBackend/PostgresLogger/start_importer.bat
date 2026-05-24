@echo off
REM ============================================================================
REM START HIGH-PERFORMANCE IMPORTER (One-Time Import)
REM Scans directory and imports all parquet files
REM ============================================================================

echo ========================================
echo HIGH-PERFORMANCE IMPORTER
echo One-Time Import Mode
echo ========================================
echo.

cd /d "%~dp0"

REM Activate virtual environment if exists
if exist venv\Scripts\activate.bat (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

echo Starting importer...
echo.

python services\high_performance_importer.py

echo.
echo ========================================
echo IMPORT COMPLETE
echo ========================================
echo.
pause
