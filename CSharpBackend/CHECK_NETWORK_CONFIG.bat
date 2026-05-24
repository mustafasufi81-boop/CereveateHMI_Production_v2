@echo off
echo ============================================================
echo OPC DA Web Browser - Network Configuration Check
echo ============================================================
echo.

REM Get local IP address
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set LOCAL_IP=%%a
    set LOCAL_IP=!LOCAL_IP:~1!
    goto :found_ip
)
:found_ip

echo Current PC IP: %LOCAL_IP%
echo.

echo ========================================
echo Configuration Status
echo ========================================
echo.

echo 1. Checking Program.cs configuration...
findstr /C:"ListenAnyIP(5001)" Program.cs >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo    ✅ Listening on all interfaces: 0.0.0.0:5001
) else (
    echo    ❌ NOT configured for network access
    echo    Please check Program.cs
)
echo.

echo 2. Checking CORS configuration...
findstr /C:"AllowAnyOrigin" Program.cs >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo    ✅ CORS enabled: AllowAnyOrigin
) else (
    echo    ⚠️  CORS may not be configured
)
echo.

echo 3. Checking Windows Firewall...
netsh advfirewall firewall show rule name="OPC DA Web Browser" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo    ✅ Firewall rule exists
) else (
    echo    ❌ Firewall rule NOT found
    echo.
    echo    Run this command as Administrator to add firewall rule:
    echo    netsh advfirewall firewall add rule name="OPC DA Web Browser" dir=in action=allow protocol=TCP localport=5001
)
echo.

echo 4. Checking if application is running...
netstat -ano | findstr ":5001" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo    ✅ Application is listening on port 5001
    echo.
    netstat -ano | findstr ":5001"
) else (
    echo    ❌ Application is NOT running
    echo.
    echo    Start it with: START_HISTORIAN_SYSTEM.bat
)
echo.

echo ========================================
echo Network Access URLs
echo ========================================
echo.
echo From this PC (192.168.0.10):
echo    http://localhost:5001
echo    http://192.168.0.10:5001
echo.
echo From HMI PC (192.168.0.120):
echo    http://192.168.0.10:5001
echo.
echo From any PC on 192.168.0.x network:
echo    http://192.168.0.10:5001
echo.

echo ========================================
echo Quick Tests
echo ========================================
echo.
echo Test 1: Check if web server responds locally
curl -s http://localhost:5001/api/opc/status 2>nul
if %ERRORLEVEL% equ 0 (
    echo    ✅ Local access OK
) else (
    echo    ❌ Application not responding locally
)
echo.

echo Test 2: Check if accessible from network IP
curl -s http://192.168.0.10:5001/api/opc/status 2>nul
if %ERRORLEVEL% equ 0 (
    echo    ✅ Network access OK
) else (
    echo    ⚠️  May not be accessible from network
    echo    Check firewall settings
)
echo.

echo ========================================
echo Next Steps
echo ========================================
echo.
echo If application is NOT running:
echo    1. Run: START_HISTORIAN_SYSTEM.bat
echo.
echo If firewall rule is missing:
echo    1. Run this script as Administrator
echo    2. Or manually add firewall rule (shown above)
echo.
echo If HMI cannot connect:
echo    1. Ensure this PC IP is 192.168.0.10
echo    2. Update HMI config if IP is different
echo    3. Test from HMI PC: curl http://192.168.0.10:5001/api/opc/status
echo.

pause
