@echo off
title Cereveate OPC Platform - Full Stack Launcher
color 0A
echo ============================================================
echo  Cereveate OPC Platform  —  Full Stack Launcher
echo ============================================================
echo.
echo  [1] C# OPC Backend          http://localhost:5001
echo  [2] Flask HMI Backend       http://localhost:6001
echo  [3] WebSocket Bridge        http://localhost:6002
echo  [4] Apex HMI (dev)          http://localhost:8080
echo ============================================================
echo.

SET ROOT=c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206
SET BRIDGE=%ROOT%\WEB_HMI_MFA\mqtt_subscriber_service
SET APEX=%ROOT%\WEB_HMI_MFA\HMI\apex-hmi

REM ── [1] C# OPC Backend (x86, port 5001) ──────────────────────
echo [1/3] Starting C# OPC Backend on port 5001...
start "C# OPC Backend :5001" cmd /k "cd /d "%ROOT%" && dotnet run -c Debug"
timeout /t 5 /nobreak >nul

REM ── [2] Flask HMI Backend (auth + APIs, port 6001) ────────────
echo [2/4] Starting Flask HMI Backend on port 6001...
start "Flask HMI Backend :6001" cmd /k "cd /d "%ROOT%\WEB_HMI_MFA\HMI" && python app.py"
timeout /t 5 /nobreak >nul

REM ── [3] WebSocket Bridge (MQTT→Socket.IO, port 6002) ───────────
echo [3/4] Starting WebSocket Bridge on port 6002...
start "WebSocket Bridge :6002" cmd /k "cd /d "%BRIDGE%" && python websocket_bridge.py"
timeout /t 3 /nobreak >nul

REM ── [4] Build Apex HMI and copy to nginx root ───────────────
echo [4/4] Building Apex HMI and deploying to C:\hmi_dist ...
cd /d "%APEX%"
call npm run build
xcopy /E /Y /I "%APEX%\dist\*" "C:\hmi_dist\" >nul
echo     Deployed to C:\hmi_dist

REM ── nginx is already running (started externally) ───────────
echo     Nginx serving at http://localhost:8080

echo.
echo ============================================================
echo  All services started!
echo  Apex HMI:   http://localhost:8080
echo  Flask API:  http://localhost:6001/api
echo  C# OPC:     http://localhost:5001/api
echo  WS Bridge:  http://localhost:6002/health
echo ============================================================
echo.
pause
