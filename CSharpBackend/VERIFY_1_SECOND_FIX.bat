@echo off
REM ====================================================================
REM Verify 1-Second Database Write Fix
REM ====================================================================
REM This script verifies the rate controller fix is working correctly
REM Expected: Data arrives every 1 second (not 5 seconds)
REM ====================================================================

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║          VERIFY 1-SECOND DATABASE WRITE FIX                        ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.
echo ✅ Code fix applied to RateControllerService.cs
echo    - Removed incorrect timer reset on filtered samples (line 177)
echo    - Timer only resets when sample is WRITTEN (not filtered)
echo.
echo 📋 To verify the fix:
echo    1. Restart OPC backend (Ctrl+C, then dotnet run)
echo    2. Wait 2 minutes for data collection
echo    3. Run diagnostic: python check_opc_polling_intervals.py
echo.
echo 🎯 Expected Results After Fix:
echo    - Timestamp distribution should be UNIFORM (all seconds 0-9)
echo    - NOT peaks at seconds 0,1,5,6 (old bug pattern)
echo    - Average interval should be ~1000ms (not ~5000ms)
echo.

pause

echo.
echo [1/2] Checking if OPC backend is running...
netstat -ano | findstr ":5001" | findstr "LISTENING"
if %ERRORLEVEL% EQU 0 (
    echo ✅ OPC backend is running on port 5001
) else (
    echo ❌ OPC backend NOT running! Start it first: dotnet run
    pause
    exit /b 1
)

echo.
echo [2/2] Running diagnostic script...
echo.
python check_opc_polling_intervals.py

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║                    ANALYSIS COMPLETE                               ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.
echo 📊 Review the "TIMESTAMP DISTRIBUTION ANALYSIS" section above
echo.
echo ✅ GOOD (Fixed): Uniform distribution across all seconds 0-9
echo    Example: Second 0: ███ 45, Second 1: ███ 47, Second 2: ███ 46...
echo.
echo ❌ BAD (Not Fixed): Peaks at seconds 0,1,5,6 only
echo    Example: Second 0: ██████ 140, Second 1: ████████ 195, Second 5: ██████ 140
echo.
echo 💡 If still showing 5-second pattern:
echo    - Make sure you RESTARTED the OPC backend after code change
echo    - Check build output for compilation errors
echo    - Verify RateControllerService.cs line 177 is removed
echo.
pause
