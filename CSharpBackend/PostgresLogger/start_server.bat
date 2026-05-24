@echo off
echo ========================================
echo Cereveate Database Trends API
echo Starting Application...
echo ========================================

cd /d "%~dp0"

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Starting FastAPI server with background importer...
echo.
echo Application will be available at:
echo   http://localhost:6001
echo.
echo Background importer will auto-start
echo Tag catalog refreshes every 60 seconds
echo Config changes detected every 10 seconds
echo.
echo Press Ctrl+C to stop the server
echo.

uvicorn api.main:app --host 0.0.0.0 --port 6001

pause
