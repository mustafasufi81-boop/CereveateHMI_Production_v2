@echo off
REM Master startup script - Starts both web server and background importer
echo ========================================
echo Cereveate Database Trends System
echo Complete Startup
echo ========================================
echo.

echo Activating virtual environment...
cd /d "%~dp0"
call venv\Scripts\activate.bat

echo.
echo Starting Web Server (Port 8001)...
start "Cereveate Web Server" cmd /k "python api\main.py"

echo.
echo Waiting 5 seconds for server to start...
timeout /t 5 /nobreak >nul

echo.
echo Starting Background Importer...
start "Cereveate Parquet Importer" cmd /k "python services\background_importer.py"

echo.
echo ========================================
echo Both services started successfully!
echo ========================================
echo.
echo Web UI: http://localhost:8001
echo.
echo Two windows opened:
echo   1. Web Server (FastAPI)
echo   2. Background Importer (Parquet Monitor)
echo.
echo Close those windows to stop the services.
echo.

pause
