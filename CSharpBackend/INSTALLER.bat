@echo off
echo ========================================
echo Cereveate_Praxis OPC Server
echo Professional Installation
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

REM ========================================
REM Installation Path Configuration
REM ========================================
set DEFAULT_INSTALL_DIR=C:\Program Files\CereveateOPC
set TASK_NAME=CereveateOPCServer

REM Auto-detect source directory (installer is in Distribution folder, files are in publish subfolder)
set SOURCE_DIR=%~dp0publish

echo Default Installation Path: %DEFAULT_INSTALL_DIR%
echo.
set /p CUSTOM_PATH="Enter custom installation path (or press Enter for default): "

if "%CUSTOM_PATH%"=="" (
    set INSTALL_DIR=%DEFAULT_INSTALL_DIR%
    echo Using default path: %INSTALL_DIR%
) else (
    set INSTALL_DIR=%CUSTOM_PATH%
    echo Using custom path: %INSTALL_DIR%
)

echo.
echo ========================================
echo Installation Configuration
echo ========================================
echo Installation Path: %INSTALL_DIR%
echo Source Files: %SOURCE_DIR%
echo.
echo This installer will:
echo  1. Copy application files to: %INSTALL_DIR%
echo  2. Create log directories (D:\OpcLogs)
echo  3. Configure DCOM for remote OPC server access
echo  4. Add Windows Firewall rules
echo  5. Set up auto-start (Task Scheduler)
echo  6. Start the application
echo.
set /p CONFIRM="Continue with installation? (Y/N): "
if /i not "%CONFIRM%"=="Y" (
    echo Installation cancelled by user.
    pause
    exit /b 0
)

REM ========================================
REM Step 1: Copy Files
REM ========================================
echo.
echo ========================================
echo [1/6] Copying Application Files
echo ========================================
echo Source: %SOURCE_DIR%
echo Destination: %INSTALL_DIR%
echo.

REM Stop existing process if running
taskkill /f /im OpcDaWebBrowser.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Stopped running application...
    timeout /t 2 /nobreak >nul
)

REM Remove old installation
if exist "%INSTALL_DIR%" (
    echo Removing old installation from: %INSTALL_DIR%
    rmdir /s /q "%INSTALL_DIR%"
    if %ERRORLEVEL% NEQ 0 (
        echo ERROR: Failed to remove old installation!
        echo Path: %INSTALL_DIR%
        echo Please close any programs using files in this directory.
        echo.
        pause
        exit /b 1
    )
)

REM Create installation directory
echo Creating directory: %INSTALL_DIR%
mkdir "%INSTALL_DIR%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create installation directory!
    echo Path: %INSTALL_DIR%
    echo Please check you have write permissions to this location.
    echo.
    pause
    exit /b 1
)

REM Copy files
echo Copying files...
xcopy /s /e /y /i "%SOURCE_DIR%\*" "%INSTALL_DIR%\" >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to copy files!
    echo Source: %SOURCE_DIR%
    echo Destination: %INSTALL_DIR%
    echo.
    echo Possible reasons:
    echo  - Insufficient permissions
    echo  - Disk space full
    echo  - Files in use by another program
    echo  - Invalid installation path
    echo.
    pause
    exit /b 1
)

echo Files copied successfully to: %INSTALL_DIR%
echo.

REM ========================================
REM Step 2: Create Log Directories
REM ========================================
echo.
echo [2/6] Creating log directories...
if not exist "D:\OpcLogs" mkdir "D:\OpcLogs"
if not exist "D:\OpcLogs\Data" mkdir "D:\OpcLogs\Data"
if not exist "D:\OpcLogs\Application" mkdir "D:\OpcLogs\Application"
if not exist "D:\BackupFile" mkdir "D:\BackupFile"
if not exist "D:\BackupFile\OpcLogs" mkdir "D:\BackupFile\OpcLogs"
echo Log directories created successfully.

REM ========================================
REM Step 3: Configure DCOM
REM ========================================
echo.
echo [3/6] Configuring DCOM for remote OPC access...
reg add "HKLM\Software\Microsoft\Ole" /v EnableDCOM /t REG_SZ /d Y /f >nul 2>&1
reg add "HKLM\Software\Microsoft\Ole" /v LegacyAuthenticationLevel /t REG_DWORD /d 2 /f >nul 2>&1
reg add "HKLM\Software\Microsoft\Ole" /v LegacyImpersonationLevel /t REG_DWORD /d 2 /f >nul 2>&1
echo DCOM configured successfully.

REM ========================================
REM Step 4: Configure Firewall
REM ========================================
echo.
echo [4/6] Configuring Windows Firewall...
netsh advfirewall firewall delete rule name="OPC DCOM" >nul 2>&1
netsh advfirewall firewall delete rule name="OPC Communication" >nul 2>&1
netsh advfirewall firewall delete rule name="Cereveate OPC Server" >nul 2>&1

netsh advfirewall firewall add rule name="OPC DCOM" dir=in action=allow protocol=TCP localport=135 >nul 2>&1
netsh advfirewall firewall add rule name="OPC Communication" dir=in action=allow protocol=TCP localport=10000-10100 >nul 2>&1
netsh advfirewall firewall add rule name="Cereveate OPC Server" dir=in action=allow program="%INSTALL_DIR%\OpcDaWebBrowser.exe" enable=yes >nul 2>&1
echo Firewall rules configured successfully.

REM ========================================
REM Step 5: Create Auto-Start Task (Boot - No Login Required)
REM ========================================
echo.
echo [5/6] Creating auto-start task...
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
)

REM Create task to run at system boot as SYSTEM (Console app works!)
schtasks /create /tn "%TASK_NAME%" /tr "\"%INSTALL_DIR%\OpcDaWebBrowser.exe\"" /sc onstart /ru "NT AUTHORITY\SYSTEM" /rl highest /f >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Failed to create auto-start task
) else (
    echo Auto-start task created successfully
    echo Application will start at system boot (no login required)
)

REM ========================================
REM Step 6: Start Application
REM ========================================
echo.
echo [6/6] Starting application...
start "" "%INSTALL_DIR%\OpcDaWebBrowser.exe"
echo Waiting for application to start...
timeout /t 8 /nobreak >nul

REM Verify application started
tasklist | find /i "OpcDaWebBrowser.exe" >nul
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Installation Complete!
    echo ========================================
    echo.
    echo Application Status: RUNNING
    echo Web Interface: http://localhost:6001
    echo Installation Path: %INSTALL_DIR%
    echo Log Directory: D:\OpcLogs
    echo Backup Directory: D:\BackupFile\OpcLogs
    echo.
    echo Default Credentials:
    echo   Administrator: opcadmin / Cereveate@2025
    echo   Viewer: admin / admin123
    echo.
    echo IMPORTANT - First Time Setup:
    echo   1. Login with opcadmin credentials
    echo   2. Click "Discover Servers" to find your OPC server
    echo   3. Select server and click "Browse Tags"
    echo   4. Select tags to monitor
    echo   5. Click "Start Monitoring"
    echo.
    echo After first setup, monitoring will auto-start on reboot.
    echo.
    echo The application will start automatically on Windows boot.
    echo.
    echo Opening web interface...
    timeout /t 3 /nobreak >nul
    start http://localhost:6001
    echo.
    echo If browser doesn't open automatically, go to: http://localhost:6001
) else (
    echo.
    echo WARNING: Application may not have started properly.
    echo Please check the logs at: D:\OpcLogs\Application
    echo You can manually start it from: %INSTALL_DIR%\OpcDaWebBrowser.exe
)

echo.
pause
