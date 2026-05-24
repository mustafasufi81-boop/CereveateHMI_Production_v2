@echo off
echo ========================================
echo Cereveate OPC DA Server - Restart
echo ========================================
echo.

echo [1/4] Stopping any running OpcDaWebBrowser processes...
taskkill /IM OpcDaWebBrowser.exe /F 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] Cleaning old build...
dotnet clean --configuration Release >nul 2>&1

echo [3/4] Building new version...
dotnet build --configuration Release --no-restore
if %ERRORLEVEL% NEQ 0 (
    echo Build FAILED! Press any key to exit...
    pause >nul
    exit /b 1
)

echo.
echo [4/4] Starting server with MaxRows=1 configuration...
echo ========================================
echo Console output below (Ctrl+C to stop):
echo ========================================
echo.

dotnet run --project OpcDaWebBrowser.csproj --no-build --configuration Release
