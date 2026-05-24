@echo off
REM ==============================================================================
REM START ALL HMI APPLICATIONS
REM ==============================================================================

echo Starting All HMI Applications...
echo.

REM Start HMI Dashboard (PostgreSQL + Historical)
echo [1/3] Starting HMI Dashboard on port 5003...
start "HMI Dashboard" cmd /k "cd /d "%~dp0HMI" && python app.py"

REM Wait 3 seconds
timeout /t 3 /nobreak >nul

REM Start MQTT PLC Dashboard (Live PLC Data)  
echo [2/3] Starting MQTT PLC Dashboard on port 5002...
start "MQTT PLC Dashboard" cmd /k "cd /d "%~dp0HMI" && python plc_mqtt_api_comparison.py"

REM Wait 3 seconds
timeout /t 3 /nobreak >nul

REM Start BI Analytics (Advanced Analysis)
echo [3/3] Starting BI Analytics on port 6004...
start "BI Analytics" cmd /k "cd /d "%~dp0HistoricalTrends" && python app.py"

echo.
echo ===============================================
echo All HMI Applications Started Successfully!
echo ===============================================
echo.
echo Access URLs:
echo   1. HMI Dashboard (Historical):    http://localhost:5003
echo   2. MQTT PLC Dashboard (Live):     http://localhost:5002  
echo   3. BI Analytics (Advanced):       http://localhost:6004
echo.
echo For Blastfurnace_Tuyer1_Pressure data, use: http://localhost:5002
echo.
pause