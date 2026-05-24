@echo off
:: ─────────────────────────────────────────────────────────────────
:: RUN_TESTS.bat  —  One-click automated test runner
:: Runs all pytest tests and opens the HTML report when done
:: ─────────────────────────────────────────────────────────────────
setlocal

set ROOT=c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206
set VENV=%ROOT%\.venv\Scripts\python.exe
set TESTS=%ROOT%\tests
set REPORT=%ROOT%\tests\test_report.html

echo.
echo =============================================
echo   Cereveate HMI Automated Test Suite
echo =============================================
echo.

:: ── Step 1: Install test dependencies ────────────────────────────
echo [1/3] Installing test dependencies...
"%VENV%" -m pip install -r "%TESTS%\requirements_test.txt" --quiet
if errorlevel 1 (
    echo ERROR: pip install failed. Check .venv path.
    pause & exit /b 1
)

:: ── Step 2: Run all tests ─────────────────────────────────────────
echo [2/3] Running tests...
echo.
"%VENV%" -m pytest "%TESTS%" ^
    --html="%REPORT%" ^
    --self-contained-html ^
    -v ^
    --tb=short ^
    --no-header ^
    -q
set EXIT_CODE=%errorlevel%

:: ── Step 3: Open HTML report ──────────────────────────────────────
echo.
echo [3/3] Opening HTML report...
if exist "%REPORT%" (
    start "" "%REPORT%"
) else (
    echo WARNING: Report file not found at %REPORT%
)

echo.
if %EXIT_CODE%==0 (
    echo ✅  ALL TESTS PASSED
) else (
    echo ❌  SOME TESTS FAILED — check report above or open test_report.html
)
echo.
pause
exit /b %EXIT_CODE%
