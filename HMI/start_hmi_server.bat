@echo off
echo ========================================
echo Starting HMI WebSocket Server
echo ========================================
echo.

cd /d "C:\Shakil\DJangoProjects\NEW_HMI\HMI"

echo Stopping existing HMI server...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *app.py*" 2>nul

echo.
echo Starting HMI server on port 6001...
python app.py

pause
