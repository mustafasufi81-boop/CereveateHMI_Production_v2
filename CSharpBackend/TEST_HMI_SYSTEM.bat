@echo off
echo ================================================================================
echo Starting HMI Complete System
echo ================================================================================
echo.

REM Check if C# service is already running
netstat -ano | findstr :5001 >nul
if %errorlevel%==0 (
    echo [OK] C# OPC Service already running on port 5001
) else (
    echo [STARTING] C# OPC Service...
    cd /d "%~dp0"
    start "OPC Service" /MIN cmd /c "dotnet run --urls http://localhost:5001"
    timeout /t 3 /nobreak >nul
)

REM Check if HMI is already running
netstat -ano | findstr :5002 >nul
if %errorlevel%==0 (
    echo [OK] HMI Flask already running on port 5002
) else (
    echo [STARTING] HMI Flask Application...
    cd /d "%~dp0\HMI"
    start "HMI Flask" /MIN cmd /c ".\venv\Scripts\activate && python app.py"
    timeout /t 3 /nobreak >nul
)

echo.
echo ================================================================================
echo System Starting...
echo ================================================================================
echo.
echo Waiting 5 seconds for services to initialize...
timeout /t 5 /nobreak >nul

echo.
echo Running comprehensive test...
echo.
cd /d "%~dp0\HMI"
python test_hmi_flow.py

echo.
echo ================================================================================
echo Open HMI Dashboard: http://localhost:5002
echo ================================================================================
pause
