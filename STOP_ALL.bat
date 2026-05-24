@echo off
echo ============================================================
echo  Stopping ALL Cereveate HMI Services
echo ============================================================
echo.

echo [1] Stopping Nginx...
taskkill /F /IM nginx.exe /T >nul 2>&1
echo     Done.

echo [2] Stopping Flask HMI + MQTT Subscriber (Python)...
taskkill /F /IM python.exe /T >nul 2>&1
echo     Done.

echo [3] Stopping OPC Backend...
taskkill /F /IM OpcDaWebBrowser.exe /T >nul 2>&1
echo     Done.

echo.
echo ============================================================
echo  All services stopped.
echo  PostgreSQL and Mosquitto kept running (Windows Services).
echo ============================================================
pause
