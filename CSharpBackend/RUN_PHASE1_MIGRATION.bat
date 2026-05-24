@echo off
REM =============================================================================
REM PHASE 1 MIGRATION EXECUTION
REM =============================================================================
REM Runs 011_phase1_timescale_reporting.sql migration
REM =============================================================================

echo.
echo ========================================================================
echo   PHASE 1 TIMESCALE REPORTING MIGRATION
echo ========================================================================
echo.
echo This will:
echo   1. Drop old v_daily_hourly_agg view
echo   2. Create ca_hourly continuous aggregate
echo   3. Add 10-minute refresh policy
echo   4. Create compatibility view
echo.
echo Press Ctrl+C to cancel, or
pause

set PGPASSWORD=cereveate@222
set PSQL_PATH=psql

echo.
echo Running migration...
echo.

%PSQL_PATH% -h localhost -U cereveate -d Automation_DB -f "WEB_HMI_MFA\HMI\migrations\011_phase1_timescale_reporting.sql"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================================
    echo   MIGRATION FAILED!
    echo ========================================================================
    echo.
    echo Check error messages above.
    echo If needed, run: RUN_PHASE1_ROLLBACK.bat
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================================================
echo   MIGRATION SUCCESSFUL!
echo ========================================================================
echo.
echo Next steps:
echo   1. Run: RUN_PHASE1_MONITORING.bat (to check system health)
echo   2. Wait 10-15 minutes for first refresh cycle
echo   3. Test report endpoints
echo   4. Monitor job status over next 24-48 hours
echo.
echo If issues occur, run: RUN_PHASE1_ROLLBACK.bat
echo.
pause
