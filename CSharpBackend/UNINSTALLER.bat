@echo off
echo ========================================
echo Cereveate_Praxis OPC Server Uninstaller
echo ========================================
echo.

REM Check for admin rights
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Administrator rights required!
    echo Please right-click this file and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

set INSTALL_DIR=C:\Program Files\CereveateOPC

echo WARNING: This will remove the Cereveate OPC Server.
echo Log files will be preserved at D:\OpcLogs
echo.
set /p CONFIRM=Are you sure you want to continue? (Y/N): 
if /i not "%CONFIRM%"=="Y" (
    echo Uninstallation cancelled.
    pause
    exit /b 0
)

echo.
echo [Step 1/5] Stopping application...
taskkill /f /im OpcDaWebBrowser.exe >nul 2>&1
timeout /t 2 /nobreak >nul
echo Application stopped.

echo [Step 2/5] Removing auto-start task...
schtasks /delete /tn "CereveateOPCServer" /f >nul 2>&1
echo Auto-start task removed.

echo [Step 3/5] Removing firewall rules...
netsh advfirewall firewall delete rule name="OPC DCOM" >nul 2>&1
netsh advfirewall firewall delete rule name="OPC Communication" >nul 2>&1
netsh advfirewall firewall delete rule name="Cereveate OPC Server" >nul 2>&1
echo Firewall rules removed.

echo [Step 4/5] Removing application files...
if exist "%INSTALL_DIR%" (
    rd /s /q "%INSTALL_DIR%"
    echo Application files removed.
) else (
    echo No installation found.
)

echo [Step 5/5] Removing desktop shortcut...
del "%USERPROFILE%\Desktop\Cereveate OPC Server.url" >nul 2>&1
echo Desktop shortcut removed.

echo.
echo ========================================
echo Uninstallation Complete!
echo ========================================
echo.
echo Log files preserved at: D:\OpcLogs
echo Backup files preserved at: D:\BackupFile\OpcLogs
echo.
echo To remove logs manually, delete:
echo   D:\OpcLogs
echo   D:\BackupFile\OpcLogs
echo.
pause
