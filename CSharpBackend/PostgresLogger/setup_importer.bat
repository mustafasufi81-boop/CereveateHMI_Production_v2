@echo off
REM ============================================================================
REM SETUP HIGH-PERFORMANCE IMPORTER
REM Run this once to initialize the database schema
REM ============================================================================

echo ========================================
echo HIGH-PERFORMANCE IMPORTER SETUP
echo ========================================
echo.

REM Check if PostgreSQL is accessible
echo [1/3] Checking PostgreSQL connection...
psql -U cereveate -d Cereveate -c "SELECT version();" > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Cannot connect to PostgreSQL
    echo Please ensure:
    echo   - PostgreSQL is running
    echo   - Database 'Cereveate' exists
    echo   - User 'cereveate' has access
    echo.
    pause
    exit /b 1
)
echo    OK - PostgreSQL connected
echo.

REM Create schema
echo [2/3] Creating database schema...
psql -U cereveate -d Cereveate -f schema_complete.sql
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Schema creation failed
    pause
    exit /b 1
)
echo    OK - Schema created
echo.

REM Verify schema
echo [3/3] Verifying tables...
psql -U cereveate -d Cereveate -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('sensor_data', 'tag_catalog', 'file_imports', 'tag_imports') ORDER BY tablename;"
echo.

echo ========================================
echo SETUP COMPLETE
echo ========================================
echo.
echo Next steps:
echo   1. Configure tag mappings in config\app_config.json
echo   2. Run: start_importer.bat (one-time import)
echo   3. Run: start_continuous_service.bat (continuous monitoring)
echo.
pause
