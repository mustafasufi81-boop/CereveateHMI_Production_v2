@echo off
echo ============================================================
echo Add Windows Firewall Rules for OPC DA Web Browser + MQTT
echo ============================================================
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

echo.
echo [1/2] Adding firewall rule for OPC DA Web Browser (port 5001)...
netsh advfirewall firewall delete rule name="OPC DA Web Browser" >nul 2>&1
netsh advfirewall firewall add rule name="OPC DA Web Browser" dir=in action=allow protocol=TCP localport=5001

echo [2/2] Adding firewall rule for MQTT Broker (port 1883)...
netsh advfirewall firewall delete rule name="MQTT Broker" >nul 2>&1
netsh advfirewall firewall add rule name="MQTT Broker" dir=in action=allow protocol=TCP localport=1883

echo.
echo ============================================================
echo ✅ Firewall rules configured!
echo ============================================================
echo.
echo Your Network IPs:
echo    WiFi (192.168.1.x): 192.168.1.39
echo    LAN  (192.168.0.x): 192.168.0.120
echo.
echo Services available:
echo    - OPC DA Web Browser: http://192.168.1.39:5001
echo    - OPC DA Web Browser: http://192.168.0.120:5001
echo    - MQTT Broker:        192.168.1.39:1883
echo    - MQTT Broker:        192.168.0.120:1883
echo.
echo Remote clients can now connect to these ports!
echo.

pause
