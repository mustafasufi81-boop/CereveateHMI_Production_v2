@echo off
echo ============================================================
echo Adding Windows Firewall Rule for HMI Server
echo ============================================================
echo.
echo This will allow remote connections to HMI on port 5002
echo Your local IP: 192.168.0.120
echo.

REM Check for administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script requires Administrator privileges
    echo Right-click and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

echo Adding firewall rule for HMI Server (port 5002)...
netsh advfirewall firewall delete rule name="HMI Server - Port 5002" >nul 2>&1
netsh advfirewall firewall add rule name="HMI Server - Port 5002" dir=in action=allow protocol=TCP localport=5002

if %errorLevel% equ 0 (
    echo.
    echo ✅ SUCCESS! Firewall rule added.
    echo.
    echo Remote devices can now access HMI at:
    echo    http://192.168.0.120:5002
    echo.
) else (
    echo.
    echo ❌ FAILED to add firewall rule
    echo.
)

echo.
echo Press any key to exit...
pause >nul
