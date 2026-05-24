@echo off
REM ============================================================================
REM MQTT Subscriber Service - Database Deployment Script
REM Deploys all required tables to PostgreSQL database
REM ============================================================================

echo.
echo ====================================================================
echo MQTT Subscriber Service - Database Deployment
echo ====================================================================
echo.

REM Check if PostgreSQL psql is available
where psql >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PostgreSQL psql command not found in PATH
    echo Please install PostgreSQL client tools or add psql to your PATH
    echo.
    pause
    exit /b 1
)

REM Database connection parameters - UPDATE THESE
set DB_HOST=localhost
set DB_PORT=5432
set DB_NAME=cerevatedb
set DB_USER=cereveate

echo Database Connection:
echo   Host: %DB_HOST%
echo   Port: %DB_PORT%
echo   Database: %DB_NAME%
echo   User: %DB_USER%
echo.

REM Prompt for password
set /p DB_PASSWORD=Enter PostgreSQL password for user %DB_USER%: 

echo.
echo Deploying database schema...
echo.

REM Set PGPASSWORD environment variable
set PGPASSWORD=%DB_PASSWORD%

REM Run the deployment SQL script
psql -h %DB_HOST% -p %DB_PORT% -U %DB_USER% -d %DB_NAME% -f "%~dp0sql\deploy_all_tables.sql"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ====================================================================
    echo Database deployment completed successfully!
    echo ====================================================================
    echo.
) else (
    echo.
    echo ====================================================================
    echo ERROR: Database deployment failed!
    echo ====================================================================
    echo.
    pause
    exit /b 1
)

REM Clear password from environment
set PGPASSWORD=

echo.
echo Next steps:
echo 1. Verify tables in pgAdmin or psql
echo 2. Create MQTT subscriber user if needed
echo 3. Update config/config.yaml with connection details
echo 4. Run tests with: python tests/test_basic.py
echo.

pause
