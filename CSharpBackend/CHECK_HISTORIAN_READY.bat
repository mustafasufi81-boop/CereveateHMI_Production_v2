@echo off
REM ============================================================================
REM HISTORIAN SERVICE - READINESS CHECK
REM Verifies all components are ready before starting
REM ============================================================================

echo ========================================
echo HISTORIAN SERVICE READINESS CHECK
echo ========================================
echo.

set ALL_OK=1

REM Check 1: Database connectivity
echo [1/6] Checking database connection...
psql -h localhost -p 5432 -U cereveate -d Cereveate -c "SELECT 1;" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Database connected
) else (
    echo [FAIL] Cannot connect to database
    echo       Please ensure PostgreSQL is running
    set ALL_OK=0
)
echo.

REM Check 2: TimescaleDB extension
echo [2/6] Checking TimescaleDB extension...
psql -h localhost -p 5432 -U cereveate -d Cereveate -c "SELECT extname FROM pg_extension WHERE extname='timescaledb';" -t | findstr "timescaledb" >nul
if %ERRORLEVEL% equ 0 (
    echo [OK] TimescaleDB extension installed
) else (
    echo [WARN] TimescaleDB extension not found
    echo        Some features may not work
)
echo.

REM Check 3: Schema exists
echo [3/6] Checking historian schema...
psql -h localhost -p 5432 -U cereveate -d Cereveate -c "SELECT schemaname FROM pg_catalog.pg_tables WHERE schemaname='historian_meta' LIMIT 1;" -t | findstr "historian_meta" >nul
if %ERRORLEVEL% equ 0 (
    echo [OK] Historian schema exists
) else (
    echo [FAIL] Historian schema not found
    echo        Run: Services\HistorianIngest\DB\SETUP_DATABASE.bat
    set ALL_OK=0
)
echo.

REM Check 4: Tag mappings
echo [4/6] Checking tag mappings...
for /f %%i in ('psql -h localhost -p 5432 -U cereveate -d Cereveate -t -c "SELECT COUNT(*) FROM historian_meta.tag_master WHERE enabled=true;" 2^>nul') do set TAG_COUNT=%%i
if defined TAG_COUNT (
    if %TAG_COUNT% gtr 0 (
        echo [OK] Found %TAG_COUNT% enabled tags
    ) else (
        echo [WARN] No tags configured
        echo        Add tags via: http://localhost:5001/historian/mapping.html
    )
) else (
    echo [SKIP] Could not check tag count
)
echo.

REM Check 5: Application built
echo [5/6] Checking application build...
if exist "bin\Debug\net8.0\win-x86\OpcDaWebBrowser.exe" (
    echo [OK] Application is built
) else (
    echo [WARN] Application not built
    echo        Building now...
    dotnet build OpcDaWebBrowser.csproj -c Debug >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        echo [OK] Build successful
    ) else (
        echo [FAIL] Build failed
        set ALL_OK=0
    )
)
echo.

REM Check 6: Configuration file
echo [6/6] Checking configuration...
if exist "appsettings.json" (
    findstr /C:"Historian" appsettings.json >nul
    if %ERRORLEVEL% equ 0 (
        echo [OK] Historian configuration found
    ) else (
        echo [WARN] Historian section missing in appsettings.json
    )
) else (
    echo [FAIL] appsettings.json not found
    set ALL_OK=0
)
echo.

echo ========================================
if %ALL_OK% equ 1 (
    echo RESULT: All checks passed!
    echo System is ready to start
    echo.
    echo Run: START_HISTORIAN_SYSTEM.bat
) else (
    echo RESULT: Some checks failed
    echo Please fix issues before starting
)
echo ========================================
echo.
pause
