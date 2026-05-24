@echo off
REM =============================================================================
REM PHASE 1 ROLLBACK EXECUTION
REM =============================================================================
REM Reverts Phase 1 changes
REM =============================================================================

echo.
echo ========================================================================
echo   PHASE 1 ROLLBACK
echo ========================================================================
echo.
echo WARNING: This will revert Phase 1 changes:
echo   - Remove continuous aggregate
echo   - Restore normal SQL view
echo   - Remove refresh policy
echo.
echo Press Ctrl+C to cancel, or
pause

set PGPASSWORD=cereveate@222
set PSQL_PATH=psql

echo.
echo Running rollback...
echo.

%PSQL_PATH% -h localhost -U cereveate -d Automation_DB -f "WEB_HMI_MFA\HMI\migrations\011_phase1_timescale_reporting_ROLLBACK.sql"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================================
    echo   ROLLBACK FAILED!
    echo ========================================================================
    echo.
    echo Check error messages above.
    echo Manual intervention may be required.
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================================================
echo   ROLLBACK SUCCESSFUL!
echo ========================================================================
echo.
echo System reverted to pre-Phase-1 state.
echo Normal SQL view restored.
echo.
pause
