@echo off
REM =============================================================================
REM PHASE 1 MONITORING EXECUTION
REM =============================================================================
REM Runs monitoring queries to check system health
REM =============================================================================

echo.
echo ========================================================================
echo   PHASE 1 MONITORING CHECK
echo ========================================================================
echo.

set PGPASSWORD=cereveate@222
set PSQL_PATH=psql

%PSQL_PATH% -h localhost -U cereveate -d Automation_DB -f "WEB_HMI_MFA\HMI\migrations\011_phase1_monitoring.sql"

echo.
echo ========================================================================
echo   MONITORING CHECK COMPLETE
echo ========================================================================
echo.
echo Review output above for any warnings or alerts.
echo.
echo Key metrics to watch:
echo   - Job failure rate should be less than 5%%
echo   - Refresh lag should be less than 30 minutes
echo   - Compression should be active
echo   - Chunk sizes should be 100MB - 10GB range
echo.
pause
