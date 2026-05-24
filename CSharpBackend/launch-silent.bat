@echo off
REM Cereveate_Praxis OPC Server - Silent Background Launcher
REM Launches application without any visible windows

set EXE_PATH=%~dp0OpcDaWebBrowser.exe

REM Check if already running
tasklist /FI "IMAGENAME eq OpcDaWebBrowser.exe" 2>NUL | find /I /N "OpcDaWebBrowser.exe">NUL
if "%ERRORLEVEL%"=="0" (
    REM Already running - exit silently
    exit /b 0
)

REM Launch silently in background
start "" /B "%EXE_PATH%"

REM Exit immediately without waiting
exit /b 0
