@echo off
echo ============================================================
echo Configure Remote C# Backend Connection
echo ============================================================
echo.
echo Current HMI: 192.168.0.120:5002
echo.
echo Enter the IP address of the PC running C# OPC Backend
echo (Example: 192.168.0.10 or leave blank for localhost)
echo.
set /p BACKEND_IP="Backend IP: "

if "%BACKEND_IP%"=="" (
    set BACKEND_IP=127.0.0.1
    echo Using localhost (127.0.0.1)
) else (
    echo Using remote backend: %BACKEND_IP%
)

echo.
echo Updating config.json...

REM Use PowerShell to update JSON (cleaner than batch string manipulation)
powershell -Command "$json = Get-Content 'config.json' | ConvertFrom-Json; $json.csharp_backend.host = '%BACKEND_IP%'; $json | ConvertTo-Json -Depth 10 | Set-Content 'config.json'"

if %errorLevel% equ 0 (
    echo.
    echo ✅ SUCCESS! Configuration updated.
    echo.
    echo Backend URL: http://%BACKEND_IP%:5001
    echo.
    echo IMPORTANT: 
    echo 1. Restart HMI for changes to take effect
    echo 2. Ensure C# backend is running on %BACKEND_IP%:5001
    echo 3. Ensure firewall allows port 5001 on backend PC
    echo.
) else (
    echo.
    echo ❌ FAILED to update configuration
    echo.
)

pause
