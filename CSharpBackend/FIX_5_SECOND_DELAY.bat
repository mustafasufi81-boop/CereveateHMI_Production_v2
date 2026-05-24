@echo off
REM ====================================================================
REM Fix 5-Second Database Write Delay
REM ====================================================================
REM Problem: Data arrives with ~5s intervals despite 1s OPC polling
REM Root Cause: Rate control with deadband filtering skips unchanged values
REM Solution: Disable rate control to capture EVERY sample
REM ====================================================================

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║          FIX 5-SECOND DATABASE WRITE DELAY                         ║
echo ╔════════════════════════════════════════════════════════════════════╝
echo.
echo This script will:
echo   1. Update appsettings.json to DISABLE rate control
echo   2. Set all tags to 1000ms (1 second) logging interval
echo   3. Remove deadband filtering
echo.
echo ⚠️  WARNING: This will write EVERY OPC sample to database!
echo    Database writes will increase significantly.
echo.
pause

echo.
echo [1/3] Backing up current appsettings.json...
copy /Y appsettings.json appsettings.json.backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
if %ERRORLEVEL% EQU 0 (
    echo ✅ Backup created
) else (
    echo ❌ Backup failed
    pause
    exit /b 1
)

echo.
echo [2/3] Updating database tag mappings...
echo    - Setting all tags to db_logging_interval_ms = 1000ms
echo    - Setting all tags to deadband_value = 0.0
echo.

powershell -Command "$env:PGPASSWORD='cereveate@222'; psql -h localhost -U cereveate -d Cereveate -c \"UPDATE historian_meta.tag_master SET db_logging_interval_ms = 1000, deadband_value = 0.0 WHERE enabled = true; SELECT COUNT(*) as updated_tags FROM historian_meta.tag_master WHERE enabled = true;\""

if %ERRORLEVEL% EQU 0 (
    echo ✅ Database updated
) else (
    echo ❌ Database update failed
    pause
    exit /b 1
)

echo.
echo [3/3] Updating appsettings.json rate control settings...
echo.

REM Use PowerShell to update JSON (safer than manual editing)
powershell -Command ^
    "$json = Get-Content 'appsettings.json' -Raw | ConvertFrom-Json; ^
     $json.Historian.RateControl.Enabled = $false; ^
     $json.Historian.RateControl.UseChangeDetection = $false; ^
     $json | ConvertTo-Json -Depth 10 | Set-Content 'appsettings.json'"

if %ERRORLEVEL% EQU 0 (
    echo ✅ appsettings.json updated
) else (
    echo ❌ Failed to update appsettings.json
    pause
    exit /b 1
)

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║                    CONFIGURATION UPDATED                           ║
echo ╔════════════════════════════════════════════════════════════════════╝
echo.
echo ✅ All changes applied successfully!
echo.
echo 📋 Next Steps:
echo    1. RESTART the OPC backend application (Ctrl+C then dotnet run)
echo    2. Wait 30 seconds for mappings to reload
echo    3. Run: python check_opc_polling_intervals.py
echo    4. Verify timestamp distribution shows uniform 1-second intervals
echo.
echo 📊 Expected Results:
echo    - Data should arrive EVERY second (not every 5 seconds)
echo    - Timestamp distribution should be FLAT (not peaks at 0,1,5,6)
echo    - All 36 tags should write at 1Hz rate
echo.
echo ⚠️  Monitor database performance after restart!
echo    Database write rate will increase 5x (from ~6/30s to ~30/30s per tag)
echo.
pause
