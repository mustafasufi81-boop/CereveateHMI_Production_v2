@echo off
echo ========================================
echo HISTORIAN DATABASE SCHEMA SETUP
echo ========================================
echo.

set PGPASSWORD=cereveate@222
set PSQL="C:\Program Files\PostgreSQL\16\bin\psql.exe"

if not exist %PSQL% (
    echo ERROR: PostgreSQL psql.exe not found
    echo Please update the path in this script
    pause
    exit /b 1
)

echo Creating historian schema in database: Cereveate
echo.

%PSQL% -h localhost -p 5432 -U cereveate -d Cereveate -f "Services\HistorianIngest\DB\historian_minimal_schema.sql"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo SUCCESS: Schema created successfully!
    echo ========================================
    echo.
    echo You can now start the application:
    echo   dotnet run
    echo.
) else (
    echo.
    echo ========================================
    echo ERROR: Schema creation failed
    echo ========================================
    echo.
)

pause
