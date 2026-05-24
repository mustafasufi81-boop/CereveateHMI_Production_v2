@echo off
echo ========================================
echo Creating Distribution Package
echo Cereveate_Praxis OPC Server v1.0
echo ========================================
echo.

REM Step 1: Build main application
echo [1/5] Building main application...
call build.bat
if %ERRORLEVEL% NEQ 0 (
    echo Build failed!
    pause
    exit /b 1
)

REM Step 2: Build LicenseGenerator
echo.
echo [2/5] Building LicenseGenerator...
cd LicenseGenerator
dotnet publish --configuration Release --runtime win-x86 --self-contained true -p:PublishSingleFile=true --output "..\bin\Release\net8.0\publish\LicenseGenerator"
cd ..

REM Step 3: Create distribution folder
echo.
echo [3/5] Creating distribution folder...
set DIST_DIR=Distribution
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
mkdir "%DIST_DIR%"

REM Step 4: Copy files
echo.
echo [4/5] Copying files to distribution...
copy "bin\Release\net8.0\publish\OpcDaWebBrowser.exe" "%DIST_DIR%\"
xcopy /E /I /Y "bin\Release\net8.0\publish\wwwroot" "%DIST_DIR%\wwwroot"
copy "bin\Release\net8.0\publish\logging-config.json" "%DIST_DIR%\" 2>nul
copy "install-service.bat" "%DIST_DIR%\" 2>nul
copy "launch-silent.bat" "%DIST_DIR%\" 2>nul
mkdir "%DIST_DIR%\Logs"
xcopy /E /I /Y "bin\Release\net8.0\publish\LicenseGenerator" "%DIST_DIR%\LicenseGenerator"

REM Create installation instructions
echo.
echo [5/5] Creating installation instructions...
(
echo ========================================
echo Cereveate_Praxis OPC Server v1.0
echo Professional Installation Package
echo ========================================
echo.
echo WHAT'S INCLUDED:
echo - OpcDaWebBrowser.exe ^(Main Application - Standalone, NO .NET required^)
echo - LicenseGenerator.exe ^(License Generation Tool^)
echo - wwwroot\ ^(Web UI Assets^)
echo - logging-config.json ^(Configuration File^)
echo - install-service.bat ^(Windows Service Installer^)
echo - launch-silent.bat ^(Silent Background Launcher^)
echo.
echo ========================================
echo INSTALLATION STEPS:
echo ========================================
echo.
echo STEP 1: GENERATE LICENSE
echo    1. Navigate to LicenseGenerator folder
echo    2. Run LicenseGenerator.exe
echo    3. Copy generated license.dat to main folder
echo.
echo STEP 2: CHOOSE INSTALLATION METHOD
echo.
echo    METHOD A - Windows Service ^(Recommended^):
echo       - Right-click install-service.bat
echo       - Select "Run as Administrator"
echo       - Service will start automatically
echo       - Access: http://localhost:5000
echo.
echo    METHOD B - Background Process:
echo       - Double-click launch-silent.bat
echo       - Application runs silently in background
echo       - Access: http://localhost:5000
echo.
echo    METHOD C - Direct Execution:
echo       - Double-click OpcDaWebBrowser.exe
echo       - Runs silently ^(no window^)
echo       - Access: http://localhost:5000
echo.
echo ========================================
echo CONFIGURATION:
echo ========================================
echo.
echo - Port: 5000 ^(default^)
echo - Logs: Logs\app-YYYYMMDD.log
echo - Data: Logs\OpcData_YYYYMMDD_HHMMSS.csv
echo - Config: logging-config.json
echo.
echo LICENSE INFORMATION:
echo - Trial Period: 4 months from generation
echo - Hardware Locked: Cannot transfer to other machines
echo - Warning: 7 days before expiry ^(logged to file^)
echo.
echo ========================================
echo SYSTEM REQUIREMENTS:
echo ========================================
echo.
echo - Windows 7/8/10/11 ^(32-bit or 64-bit^)
echo - NO .NET installation required
echo - NO additional downloads needed
echo - ~100 MB disk space
echo - Administrator rights ^(for Windows Service only^)
echo.
echo ========================================
echo SUPPORT:
echo ========================================
echo.
echo Company: Cereveate_Praxis
echo Product: OPC Server Professional
echo Version: 1.0
echo.
echo For technical support, please contact your system administrator.
echo.
) > "%DIST_DIR%\INSTALLATION.txt"

REM Create ZIP archive
echo.
echo Creating ZIP archive...
powershell Compress-Archive -Path "%DIST_DIR%\*" -DestinationPath "CereveateOPCServer_v1.0_Standalone.zip" -Force

echo.
echo ========================================
echo DISTRIBUTION PACKAGE CREATED!
echo ========================================
echo.
echo Location: %CD%\CereveateOPCServer_v1.0_Standalone.zip
echo Size: ~60-80 MB
echo.
echo This package is 100%% STANDALONE:
echo   - NO .NET installation required
echo   - NO NuGet packages to download
echo   - NO external dependencies
echo   - Extract and run!
echo.
echo Distribution folder: %CD%\%DIST_DIR%
echo.
pause
