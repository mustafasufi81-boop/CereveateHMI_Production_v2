@echo off
REM ============================================================================
REM COMPLETE HISTORIAN SYSTEM STARTUP
REM Starts OPC DA Service with Historian Ingest Pipeline
REM ============================================================================

echo ========================================
echo CEREVEATE HISTORIAN SYSTEM
echo Complete System Startup
echo ========================================
echo.

cd /d "%~dp0"

REM Check if database is accessible
echo Step 1: Checking database connection...
psql -h localhost -p 5432 -U cereveate -d Cereveate -c "SELECT 1;" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNING: Cannot connect to database
    echo The historian service may not start properly
    echo Please ensure PostgreSQL is running
    echo.
    pause
)

echo Database OK
echo.

REM Check if schema exists
echo Step 2: Verifying historian schema...
psql -h localhost -p 5432 -U cereveate -d Cereveate -c "SELECT COUNT(*) FROM historian_meta.tag_master;" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo WARNING: Historian schema not found!
    echo Please run: Services\HistorianIngest\DB\SETUP_DATABASE.bat
    echo.
    set /p CONTINUE="Continue anyway? (y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
)

echo Schema OK
echo.

REM Build the application
echo Step 3: Building application...
dotnet build OpcDaWebBrowser.csproj -c Debug
if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Build failed
    pause
    exit /b 1
)

echo Build successful
echo.

echo Step 4: Starting Historian System...
echo.
echo Services that will start:
echo   - OPC DA Service (data acquisition)
echo   - Historian Ingest Pipeline (rate control + batching)
echo   - Database Writer (TimescaleDB)
echo   - SignalR Hub (real-time updates)
echo   - Web UI (http://localhost:5001)
echo.
echo Press Ctrl+C to stop the system
echo.

REM Run the application
dotnet run --project OpcDaWebBrowser.csproj

echo.
echo ========================================
echo System stopped
echo ========================================
pause
