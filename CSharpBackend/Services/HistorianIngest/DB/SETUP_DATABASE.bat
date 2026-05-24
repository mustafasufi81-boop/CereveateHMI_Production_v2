@echo off
REM ============================================================================
REM Historian Database Setup Script
REM Initializes TimescaleDB schema for historian ingest system
REM ============================================================================

echo ========================================
echo HISTORIAN DATABASE SETUP
echo ========================================
echo.

set PSQL_PATH=C:\Program Files\PostgreSQL\15\bin\psql.exe
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=Cereveate
set DB_USER=cereveate
set DB_PASSWORD=cereveate@222

REM Check if psql exists
if not exist "%PSQL_PATH%" (
    echo ERROR: PostgreSQL psql.exe not found at: %PSQL_PATH%
    echo Please update PSQL_PATH in this script to match your installation
    pause
    exit /b 1
)

echo Step 1: Checking database connection...
echo.
"%PSQL_PATH%" -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "SELECT version();" 2>nul
if %ERRORLEVEL% neq 0 (
    echo ERROR: Cannot connect to database
    echo Please verify:
    echo   - PostgreSQL is running
    echo   - Database '%DB_NAME%' exists
    echo   - User '%DB_USER%' has access
    echo   - Password is correct
    pause
    exit /b 1
)

echo Connection successful!
echo.

echo Step 2: Enabling TimescaleDB extension...
"%PSQL_PATH%" -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"
if %ERRORLEVEL% neq 0 (
    echo WARNING: TimescaleDB extension may not be installed
    echo Install from: https://www.timescale.com/
)
echo.

echo Step 3: Running schema migration...
set PGPASSWORD=%DB_PASSWORD%
"%PSQL_PATH%" -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -f "%~dp0schema_migration.sql"
if %ERRORLEVEL% neq 0 (
    echo ERROR: Schema migration failed
    pause
    exit /b 1
)
echo.

echo Step 4: Verifying schema...
"%PSQL_PATH%" -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -c "SELECT schemaname FROM pg_catalog.pg_tables WHERE schemaname LIKE 'historian%%' GROUP BY schemaname ORDER BY schemaname;"
echo.

echo ========================================
echo DATABASE SETUP COMPLETE!
echo ========================================
echo.
echo Next steps:
echo 1. Add tag mappings via web UI or API
echo 2. Start the application: dotnet run
echo 3. Monitor dashboard: http://localhost:5001/historian/dashboard.html
echo.
pause
