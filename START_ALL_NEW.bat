@echo off
echo ================================================================================
echo STARTING ALL CEREVEATE HMI SERVICES
echo ================================================================================

echo.
echo [1/4] Starting C# Backend (OpcDaWebBrowser)...
cd /d "d:\CereveateHMI_Production\CSharpBackend\bin\Release\net8.0\win-x86\publish"
start "C# Backend - OpcDaWebBrowser" OpcDaWebBrowser.exe
timeout /t 3 /nobreak >nul
echo     Started.

echo [2/4] Starting Flask Backend (Python app.py)...
cd /d "d:\CereveateHMI_Production\HMI"
start "Flask Backend - Port 6001" cmd /k "python app.py"
timeout /t 3 /nobreak >nul
echo     Started on port 6001.

echo [3/4] Starting Nginx (Frontend Server)...
cd /d "d:\CereveateHMI_Production\HMI\nginx-1.28.0"
start "Nginx - Port 8090" nginx.exe
timeout /t 2 /nobreak >nul
echo     Started on port 8090.

echo [4/4] Opening HMI in browser...
timeout /t 2 /nobreak >nul
start http://localhost:8090
echo     Browser opened.

echo.
echo ================================================================================
echo ALL SERVICES STARTED SUCCESSFULLY
echo ================================================================================
echo.
echo Services Status:
echo   - C# Backend (OpcDaWebBrowser)  : Running in separate window
echo   - Flask Backend                 : Running in separate window (port 6001)
echo   - Nginx Frontend                : Running in background (port 8090)
echo   - PostgreSQL                    : Windows Service (should be running)
echo   - Mosquitto MQTT                : Windows Service (should be running)
echo.
echo HMI URL: http://localhost:8090
echo.
echo ================================================================================
pause
