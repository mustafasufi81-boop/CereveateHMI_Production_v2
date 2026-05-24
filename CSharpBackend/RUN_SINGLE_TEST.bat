@echo off
:: Run a single test file only
:: Usage:   RUN_SINGLE_TEST.bat test_reports.py
::          RUN_SINGLE_TEST.bat test_reports.py::test_daily_report_avg_calculation

set ROOT=c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206
set VENV=%ROOT%\.venv\Scripts\python.exe
set TESTS=%ROOT%\tests

if "%1"=="" (
    echo Usage: RUN_SINGLE_TEST.bat <test_file.py> [::test_name]
    echo.
    echo Available test files:
    echo   test_auth.py
    echo   test_alarms.py
    echo   test_reports.py
    echo   test_historical.py
    echo   test_db_calculations.py
    pause & exit /b 1
)

"%VENV%" -m pytest "%TESTS%\%1" -v --tb=long --no-header
pause
