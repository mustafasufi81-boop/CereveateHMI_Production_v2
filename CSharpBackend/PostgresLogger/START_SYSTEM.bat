@echo off
echo ========================================
echo PostgresLogger - Complete System Start
echo ========================================
echo.

cd /d "%~dp0"

echo [1/3] Stopping any existing Python processes...
taskkill /F /IM python.exe 2>NUL
timeout /t 2 /nobreak >NUL

echo.
echo [2/3] Starting API Server (Port 6001)...
echo        - Web UI will be available at http://localhost:6001
echo        - Background importer will auto-start
echo.

start "PostgresLogger API Server" cmd /k ".\venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 6001"

timeout /t 3 /nobreak >NUL

echo.
echo [3/3] Checking if server started...
netstat -ano | findstr :6001 >NUL
if %ERRORLEVEL% EQU 0 (
    echo ✓ Server is running!
) else (
    echo ✗ Server failed to start. Check the window for errors.
)

echo.
echo ========================================
echo System Started!
echo ========================================
echo.
echo Open in browser: http://localhost:6001
echo.
echo The background importer will:
echo  - Auto-discover tags from parquet files
echo  - Check for new mappings every 10 seconds
echo  - Import data automatically when you map tags
echo.
echo Press any key to exit this window...
pause >NUL
