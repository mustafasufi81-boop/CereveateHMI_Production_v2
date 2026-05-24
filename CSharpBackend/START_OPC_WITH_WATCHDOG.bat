@echo off
REM ============================================================
REM  OPC Backend Watchdog — auto-restarts OpcDaWebBrowser.exe
REM  whenever it crashes (heap corruption 0xc0000374, etc.)
REM ============================================================
setlocal

set "EXE_DIR=%~dp0bin\Release\net8.0\win-x86"
set "EXE_NAME=OpcDaWebBrowser.exe"
set "WATCHDOG_LOG=D:\OpcLogs\AppLogs\watchdog.log"

if not exist "D:\OpcLogs\AppLogs" mkdir "D:\OpcLogs\AppLogs"

echo [%date% %time%] Watchdog started >> "%WATCHDOG_LOG%"
echo ============================================================
echo  OPC Backend Watchdog
echo  Exe: %EXE_DIR%\%EXE_NAME%
echo  Log: %WATCHDOG_LOG%
echo  Ctrl+C in THIS window to stop completely.
echo ============================================================

:RESTART_LOOP
echo [%date% %time%] Starting %EXE_NAME%...
echo [%date% %time%] Starting %EXE_NAME% >> "%WATCHDOG_LOG%"

pushd "%EXE_DIR%"
"%EXE_NAME%"
set "EXITCODE=%ERRORLEVEL%"
popd

echo [%date% %time%] %EXE_NAME% exited with code %EXITCODE%
echo [%date% %time%] %EXE_NAME% exited with code %EXITCODE% >> "%WATCHDOG_LOG%"

REM Exit code 0 = clean shutdown (user closed it). Don't restart.
if "%EXITCODE%"=="0" (
    echo Clean exit. Watchdog stopping.
    echo [%date% %time%] Clean exit. Watchdog stopping. >> "%WATCHDOG_LOG%"
    goto :EOF
)

REM Crashed (any non-zero code, including 0xc0000374 native crash).
REM Wait 3 seconds then restart. Avoids tight restart loop.
echo Crash detected (code %EXITCODE%). Restarting in 3 seconds...
timeout /t 3 /nobreak > nul
goto RESTART_LOOP
